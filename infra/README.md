# GCP development infrastructure

Terraform defines a development environment in an existing GCP project:

- A private Cloud Run service for the FastAPI API and a separate Alembic migration job.
- Cloud SQL for PostgreSQL 17, using the Enterprise edition and a small single-zone instance.
- An Artifact Registry Docker repository for application images.
- Secret Manager source credentials and application secret versions for the database URL and OpenRouter API key.
- A dedicated runtime service account with access to its database, secrets and invoice bucket.
- A private Cloud Storage bucket for original invoice PDFs, plus a separate versioned bucket for Terraform state.

Cloud Run sends request and application output to Cloud Logging automatically.
The default region is `europe-west2` (London). This is a development setup;
Cloud SQL incurs charges while running, including before the API is deployed.
Configure billing alerts for the project.

**PDF storage integration is a follow-up application change.** This configuration
creates the bucket, grants read/create access and supplies `INVOICE_BUCKET` to the
API. The current API does not yet upload PDF bytes or save object references.

## Prerequisites

Use PowerShell 7, Terraform 1.11 or later, the Google Cloud CLI, and a running
Linux Docker engine. Choose an existing project with billing enabled and an
account permitted to create the resources above and their IAM bindings.
The following commands are deployment instructions; they create billable
resources when you run `terraform apply`.

Run commands from the repository root. Keep the same PowerShell session for the
steps below, and replace the example project ID:

```powershell
$projectId = "your-gcp-project-id"
$region = "europe-west2"
$env:TF_VAR_project_id = $projectId
$env:TF_VAR_region = $region

gcloud auth login
gcloud auth application-default login
gcloud config set project $projectId
gcloud services enable serviceusage.googleapis.com cloudresourcemanager.googleapis.com storage.googleapis.com --project=$projectId
gcloud auth application-default set-quota-project $projectId
```

Terraform uses Application Default Credentials; Docker and the later `gcloud`
commands use your Google Cloud CLI login. Each command must succeed before
continuing to the next step.

## Validate without a cloud account

These checks download the pinned provider and use mocked plans. They do not
connect to GCP or create resources:

```powershell
terraform fmt -check -recursive infra
terraform -chdir=infra/bootstrap init -backend=false
terraform -chdir=infra/bootstrap validate
terraform -chdir=infra/bootstrap test
terraform -chdir=infra/terraform init -backend=false
terraform -chdir=infra/terraform validate
terraform -chdir=infra/terraform test
```

## 1. Create and configure remote state

Bootstrap creates the state bucket and two empty source-secret containers.
Grant your Terraform operator account read access to those secrets using its
email (the account used for Application Default Credentials):

```powershell
$operatorEmail = Read-Host "Terraform operator Google account email"
$env:TF_VAR_credential_reader_members = ConvertTo-Json -InputObject @("user:$operatorEmail") -Compress
terraform -chdir=infra/bootstrap init
terraform -chdir=infra/bootstrap plan
terraform -chdir=infra/bootstrap apply
$stateBucket = terraform -chdir=infra/bootstrap output -raw state_bucket_name
```

For the first setup, bootstrap uses local state because the GCS backend needs
an existing bucket. If you already migrated bootstrap state, keep its current
backend configuration and run plan/apply to add the source secrets; skip the
state migration commands below. Use the same `name_prefix` for both stacks
if overriding the default `invoice-dev`.

Preserve a copy of the initial state, then enable the bootstrap module's remote
backend and accept Terraform's state-migration prompt:

```powershell
Copy-Item infra/bootstrap/terraform.tfstate infra/bootstrap/terraform.tfstate.pre-migration
Copy-Item infra/bootstrap/backend.tf.example infra/bootstrap/backend.tf
terraform -chdir=infra/bootstrap init -migrate-state -backend-config="bucket=$stateBucket" -backend-config="prefix=bootstrap"

Copy-Item infra/terraform/backend.hcl.example infra/terraform/backend.hcl
# Edit infra/terraform/backend.hcl and set bucket=$stateBucket.
terraform -chdir=infra/terraform init -backend-config=backend.hcl
```

For subsequent sessions, keep using the same ignored `backend.hcl` and initialize
each module with its existing bucket and prefix. Do not create a new empty state for
resources already managed by an existing state. The state bucket uses object
versioning, private access and backend locking. [GCS backend documentation](https://docs.hashicorp.com/terraform/language/backend/gcs)

## 2. Create supporting resources

Add the initial credential values once through the Google Cloud console:

1. Open **Secret Manager** in your project.
2. Open `invoice-dev-database-password`, choose **Add new version**, and enter
   the database password (at least 16 characters).
3. Open `invoice-dev-openrouter-source-key` and add the OpenRouter API key as
   a new version.
4. Note the version numbers. New secrets start at version `1`.

The names change with `name_prefix`. Run
`terraform -chdir=infra/bootstrap output credential_secret_ids` to list them.
The operator needs permission to add these
versions in the console, as well as Secret Accessor on the two source secrets
for planning. Bootstrap grants the accessor role to `credential_reader_members`.
[Adding secret versions](https://docs.cloud.google.com/secret-manager/docs/add-secret-version)

Copy the appropriate environment template and keep the real file local:

```powershell
Copy-Item infra/terraform/environments/dev.tfvars.example infra/terraform/environments/dev.tfvars
```

Only non-sensitive version numbers are supplied to Terraform. Pass the
environment file explicitly on every plan and apply:

```powershell
$env:TF_VAR_database_credentials_version = "1"
$env:TF_VAR_openrouter_key_version = "1"
terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform plan -var-file=environments/dev.tfvars
terraform -chdir=infra/terraform apply -var-file=environments/dev.tfvars
```

Terraform reads these exact source versions using the Google provider's
**ephemeral Secret Manager resource**. The values flow only into write-only
database-password and application-secret arguments; plaintext is omitted from
state and saved plans. No password or API key input variables are declared, so
plans do not prompt for them. Do not replace the ephemeral reader with a normal
secret-value data source, which would store the value in Terraform state.
[Ephemeral Secret Manager reads](https://registry.terraform.io/providers/hashicorp/google/latest/docs/ephemeral-resources/secret_manager_secret_version)

For an existing database, seed the source secrets with the credentials already
in use. Existing SQL-user and application-secret resource addresses stay the
same. If changing a credential during this upgrade, create a source version
with a number greater than the previously configured update counter, and set
the corresponding version variable to that number. The Secret Manager API is
now owned by bootstrap; removing its old main-stack entry does not disable it.

`deploy_application` defaults to `false`: the database, secrets, storage and
image repository are created first. An existing application image is therefore
not required for the initial apply. Optional non-secret configuration is shown
in the environment templates under `infra/terraform/environments`; real
`.tfvars` files remain ignored.

The database uses a public IP with no authorized networks. Cloud Run connects
through the authenticated, encrypted Cloud SQL integration and its `/cloudsql`
socket; direct database connections are not opened to the internet. The
application remains IAM-authenticated. The API also records the authenticated
verified Google token subject as the invoice owner; set `admin_members` for identities that
need to view all invoices. The PDF bucket enforces public access
prevention and uniform bucket-level IAM access.

Terraform passes `DATABASE_URL_SECRET_VERSION` and
`OPENROUTER_API_KEY_SECRET_VERSION` as numbered resource references. The Python
application reads their values directly through the Secret Manager client,
using its runtime identity, verifies payload checksums and caches successful
reads in memory. The migration job receives only the database reference.
Startup loads the database secret and executes `SELECT 1` before accepting
requests. Secret reads have a 10-second timeout, database connections use a
10-second connection timeout, and the startup connection/query phase is limited
to 15 seconds. Database failures prevent startup. OpenRouter credentials remain
lazy, so the startup check does not verify model access or application tables.
Cloud Run keeps one instance warm, which incurs idle-instance charges and reduces
delays after inactivity; instance replacements can still require startup.
Local `.env` credentials remain available when no
secret-version references are configured.

## 3. Build and push an application image

For automated releases, follow [CI/CD setup](../docs/ci-cd.md). The commands below
also support a manual release. Terraform initializes image fields on creation;
subsequent image updates belong to the release pipeline or explicit gcloud commands.

```powershell
$imageRepository = terraform -chdir=infra/terraform output -raw image_repository
$revision = git rev-parse --short HEAD
$imageName = "$imageRepository/api"
$imageTag = "${imageName}:$revision"

gcloud auth configure-docker "${region}-docker.pkg.dev"
docker build --platform linux/amd64 --tag $imageTag .
docker push $imageTag
$digest = gcloud artifacts docker images describe $imageTag --project=$projectId --format="value(image_summary.digest)"
$env:TF_VAR_container_image = "${imageName}@$digest"
```

The Docker build includes production dependencies and migration files. Build
ignore files exclude credentials, local environments, benchmark documents and
Terraform state. Deployment uses the image digest so the selected build does
not change when a tag moves. This is the manual bootstrap path; after CI/CD is
configured, Google Cloud Build performs the production build described in
`docs/ci-cd.md`.

Keep the deployed image digest, `deploy_application = true`, model identifier,
and invoker principals in your ignored environment-specific `.auto.tfvars` file
so future plans retain the deployed service configuration.

## 4. Deploy, migrate and verify

```powershell
$env:TF_VAR_openrouter_model = Read-Host "OpenRouter model identifier"
$invokerEmail = Read-Host "Google account email allowed to call the API"
$env:TF_VAR_invoker_members = ConvertTo-Json -InputObject @("user:$invokerEmail") -Compress
$env:TF_VAR_deploy_application = "true"
terraform -chdir=infra/terraform plan -var-file=environments/dev.tfvars
terraform -chdir=infra/terraform apply -var-file=environments/dev.tfvars

$migrationJob = terraform -chdir=infra/terraform output -raw migration_job_name
gcloud run jobs update $migrationJob --image=$env:TF_VAR_container_image --project=$projectId --region=$region
gcloud run jobs execute $migrationJob --project=$projectId --region=$region --wait
# Replace invoice-dev-api if using another name_prefix.
gcloud run services update invoice-dev-api --image=$env:TF_VAR_container_image --project=$projectId --region=$region
gcloud run services update-traffic invoice-dev-api --to-latest --project=$projectId --region=$region
```

The job runs `alembic upgrade head` with the same image and database connection
as the API. **Wait for a successful migration before using invoice endpoints.**
Terraform creates the job but does not execute it. Run it again after deploying
an image containing new migrations. [Executing Cloud Run jobs](https://docs.cloud.google.com/run/docs/execute/jobs)

Test the private service using an account with Cloud Run Invoker permission:

```powershell
$serviceUrl = terraform -chdir=infra/terraform output -raw service_url
$token = gcloud auth print-identity-token
$headers = @{ Authorization = "Bearer $token"; 'X-API-Authorization' = "Bearer $token" }
Invoke-RestMethod -Uri "$serviceUrl/health" -Headers $headers
Invoke-RestMethod -Uri "$serviceUrl/v1/invoices" -Headers $headers
```

The API verifies the Google signature, issuer, expiration, audience, and caller
allowlist independently of Cloud Run IAM. It never trusts plain
`X-Goog-Authenticated-User-*` headers. Set `api_token_audiences` explicitly before
deploying. Service-account tokens normally target the service URL; browser login
tokens target your OAuth client ID. For this development environment only,
`gcloud auth print-identity-token` uses the Google Cloud CLI OAuth client ID
`32555940559.apps.googleusercontent.com`, which must be explicitly allowed when
using that development token. Do not include it in production environments.
Sending both headers lets Cloud Run check `Authorization` while the API verifies
the intact signed token in `X-API-Authorization`. This is necessary because
Cloud Run can modify the standard authorization headers. Swagger's Authorize
button accepts `Bearer <token>` for the `X-API-Authorization` scheme when
accessing `/docs` through the local proxy.
Unlisted callers receive 403; missing/invalid tokens receive 401. Existing rows
without an owner remain visible only to explicitly configured admins.

You can add further specific users or service accounts through `invoker_members`,
for example `["user:you@example.com"]` in your non-secret configuration. The
configuration does not grant public access. After the health check, upload a
synthetic invoice, retrieve the stored result, and repeat the upload to verify
caching. Inspect application logs in the Cloud Run console.

## Updates and cleanup

- To rotate a credential, add a new version to its bootstrap source secret in
  the Google Cloud console. Set `database_credentials_version` or
  `openrouter_key_version` to that actual new version number, then review and
  apply the plan. The database password and generated database URL update
  together. Do this during a development maintenance window: existing API
  instances can still have the old database credentials cached until the new
  revision is serving. Deployments pin the resulting application secret versions.
- For an application update, push another image, set `container_image` to its
  digest, review the Terraform plan, apply it and run migrations before using
  the new invoice endpoints.
- The old `TF_VAR_database_password` and `TF_VAR_openrouter_api_key` environment
  variables are no longer used and can be cleared from existing shell sessions.
- Deletion protection is enabled by default. For deliberate development
  teardown, set `deletion_protection=false` and apply that change before
  destroying the application stack. Non-empty PDF and state buckets are not
  force-deleted. Preserve the state bucket until you have finished managing
  the resources recorded in it.
