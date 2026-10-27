# CI/CD with GitHub Actions, Cloud Build and Cloud Run

The workflow in `.github/workflows/ci-cd.yml` tests every PR and push to `main`.
Deployments run after successful CI on `main`, or a manual run on `main`, once
the repository variable `GCP_DEPLOY_ENABLED` is set to `true`.

## What happens

1. Start disposable PostgreSQL 17, install Python 3.12 and locked dependencies,
   and run the application and release-orchestration tests.
2. Apply Alembic migrations to the disposable database. Check Terraform
   formatting, validate all three stacks, and run their mocked tests. Build
   the production Docker image. These steps need no GCP credentials or model key.
3. On `main`, authenticate to GCP with GitHub OIDC and Workload Identity
   Federation. There is no downloaded service-account key.
4. Upload the allowlisted application source to a private staging bucket. Google
   Cloud Build builds the production container and pushes the commit-SHA tag to
   Artifact Registry. GitHub reads the immutable digest from the completed build;
   that digest is the release identifier for both the API and migration job.
5. Update and execute the migration job. A failure stops deployment before
   changing API traffic. Migrations must remain compatible with the old revision.
6. Mint a short-lived Google ID token for the deployer, targeting the canonical
   service URL. Deploy a tagged candidate revision with zero normal traffic.
7. Check `/health` and authenticated `/v1/invoices` on the candidate URL. The
   application verifies the token carried in `X-API-Authorization`; Cloud Run
   IAM verifies `Authorization`. Both use the canonical service audience.
8. Promote to 100% traffic, remove the temporary tag, and check the canonical URL.
   A rollout failure restores the previous image as the latest revision. The run
   still fails so the failure is visible. Rollback does not reverse migrations.

Deployments are serialized and never automatically cancel an active deployment.
PR jobs have read-only GitHub permissions and no cloud identity. Action versions
are pinned to commit SHAs. Cloud Build runs with a dedicated build identity and
stores logs in Cloud Logging. Manual cancellation or a runner outage can interrupt
rollback; inspect Cloud Run before starting another release in that case.

## One-time setup (operator)

The existing application stack must already exist. `infra/cicd` manages the
GitHub deployment account, dedicated Cloud Build account, private source-staging
bucket, federation provider, API enablement and resource-scoped IAM grants in its
own state. It does not manage the application, database or runtime secrets.

```powershell
Copy-Item infra/cicd/terraform.tfvars.example infra/cicd/terraform.tfvars
Copy-Item infra/cicd/backend.hcl.example infra/cicd/backend.hcl
# Edit project_id and the backend bucket. Keep prefix=cicd (not invoice-platform).
terraform -chdir=infra/cicd init -backend-config=backend.hcl
terraform -chdir=infra/cicd plan
terraform -chdir=infra/cicd apply
terraform -chdir=infra/cicd output
```

The example uses this repository's immutable numeric GitHub IDs. For a fork,
obtain its repository and owner IDs using `gh api repos/OWNER/REPO`. Federation
requires those IDs, `refs/heads/main`, the `development` environment, and this
workflow's exact path. A PR, different workflow, or different branch cannot
assume the deployer identity. The GitHub account may submit Cloud Builds, stage
source in the dedicated bucket, update the service/job and use the runtime and
builder identities. The builder may read staged source, write Cloud Logging logs,
and push only to the application image repository. Neither account receives
Terraform-state access, direct Secret Manager access, or an administrator role.

In the ignored application environment file, include the deployer in
`invoker_members` alongside your existing users. This grants both Cloud Run
invocation and the API's caller allowlist. Include the canonical service URL in
`api_token_audiences`. Leave `admin_members` unchanged: smoke tests do not need
administrative access. Plan and apply `infra/terraform` with that environment file.

```hcl
invoker_members = [
  "user:you@example.com",
  "serviceAccount:invoice-dev-deployer@YOUR_PROJECT.iam.gserviceaccount.com",
]
api_token_audiences = ["https://YOUR_SERVICE.run.app"]
```

Keep any explicitly configured development CLI audience if you still use it.
Create a GitHub environment named `development`; restrict deployment branches to
`main` and optionally require approval. Add these environment variables in GitHub:

| Variable | Value |
|---|---|
| `GCP_PROJECT_ID` | Existing project ID |
| `GCP_REGION` | `europe-west2` |
| `GCP_SERVICE` | `invoice-dev-api` |
| `GCP_MIGRATION_JOB` | `invoice-dev-migrate` |
| `GCP_IMAGE_REPOSITORY` | `europe-west2-docker.pkg.dev/PROJECT/invoice-dev-images` |
| `GCP_SERVICE_URL` | Canonical URL from `terraform output -raw service_url` |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `workload_identity_provider` output of `infra/cicd` |
| `GCP_DEPLOYER_SERVICE_ACCOUNT` | `deployer_service_account` output of `infra/cicd` |
| `GCP_BUILD_SERVICE_ACCOUNT` | `build_service_account` output of `infra/cicd` |
| `GCP_BUILD_SOURCE_BUCKET` | `build_source_bucket` output of `infra/cicd` |

Set `GCP_DEPLOY_ENABLED=true` as a **repository variable** last. The workflow's job
condition needs it before environment-level variables are loaded. These values
are identifiers, not credentials; no GitHub secrets containing keys are needed.
Run the workflow manually on `main` to verify the first release. Configure branch
protection to require the `ci` job before merging subsequent PRs.

## Terraform and release ownership

Terraform creates the service and job using `container_image`. Subsequent image
changes belong to the release pipeline; lifecycle rules ignore their image fields
so an infrastructure apply cannot silently redeploy an older image from tfvars.
Terraform still manages runtime identity, secrets references, resources, scaling,
network settings and the steady-state latest-revision traffic policy. The pipeline
restores that policy after promotion or rollback. No broad `ignore_changes` or
Terraform-state permissions are used for deployments.

After this change, setting `container_image` and applying Terraform is sufficient
for initial creation only. For an existing service, use this workflow or explicitly
update the migration job image, execute it successfully, then update the service
image. An infrastructure apply must not run concurrently with a release.

## Manual recovery

Use a previously verified image digest. Update and wait for the service, then
route to the latest revision. Remove any abandoned `ci-*` traffic tag shown by
`gcloud run services describe`. Do not roll back the database automatically.

```powershell
gcloud run services update invoice-dev-api --image=PREVIOUS_IMAGE_DIGEST --project=PROJECT --region=europe-west2
gcloud run services update-traffic invoice-dev-api --to-latest --project=PROJECT --region=europe-west2
```

See the [Google federation setup guide](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines),
the [Cloud Build user-managed service account guide](https://docs.cloud.google.com/build/docs/securing-builds/configure-user-specified-service-accounts),
and [Cloud Run rollout documentation](https://docs.cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration).
