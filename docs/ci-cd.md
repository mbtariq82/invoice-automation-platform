# CI/CD with GitHub Actions, Cloud Build and Cloud Deploy

The workflow in `.github/workflows/ci-cd.yml` tests every pull request and push
to `main`. A successful `main` build deploys when the repository variable
`GCP_DEPLOY_ENABLED` is `true`.

## Release flow

1. GitHub Actions starts PostgreSQL 17, installs the locked Python 3.12
   dependencies, runs all tests and an online Alembic migration, validates and
   tests all Terraform stacks, and builds the production image locally.
2. On `main`, GitHub exchanges its OIDC token for the narrowly scoped deployer
   service account through Workload Identity Federation. No long-lived key is
   stored in GitHub.
3. Cloud Build builds the same commit with its dedicated builder identity,
   pushes it to Artifact Registry, and returns the immutable image digest.
4. The workflow exports the current Cloud Run service manifest and removes only
   server-generated fields, traffic and the old image. This preserves the
   Terraform-managed environment, secret references, service account, network,
   resource and scaling settings in the Cloud Deploy release.
5. GitHub creates a Cloud Deploy release that maps the logical `invoice-api`
   image to the digest. Cloud Deploy records and owns the rollout from here.
6. A predeploy hook updates the migration job to that digest and waits for the
   migration to succeed. The hook is idempotent and runs before API traffic
   changes. Database changes must remain compatible with the old revision.
7. Cloud Deploy sends 10%, then 50%, then 100% of traffic to the new revision.
   Each phase verifies `/health` and authenticated `/v1/invoices` against the
   exact candidate revision. Successful phases advance automatically.
8. A failed rollout is retried once and then rolled back to the last successful
   Cloud Deploy release. Database migrations are deliberately not reversed.

Deployments are serialized and never automatically cancel an active rollout.
PR jobs have read-only GitHub permissions and no cloud identity. GitHub Action
versions and task-container images are pinned. Cloud Deploy provides rollout
history, phase status and job logs in the Google Cloud console.

The first release created after introducing Cloud Deploy has no earlier Cloud
Deploy release to restore. Monitor that rollout; native automatic rollback is
available from the second successful release onward. Google may also treat the
first deployment to an existing target as the initial stable deployment rather
than split it through every canary percentage.

## One-time setup

The application stack must already exist. `infra/cicd` creates the federation
provider, GitHub deployer, Cloud Build builder, Cloud Deploy execution identity,
private staging bucket, delivery pipeline, Cloud Run target, automation, API
enablement, a deletion-safe release-artifact bucket, and resource-scoped IAM
grants. It has separate Terraform state and does not manage the database or
runtime secrets.

```powershell
Copy-Item infra/cicd/terraform.tfvars.example infra/cicd/terraform.tfvars
Copy-Item infra/cicd/backend.hcl.example infra/cicd/backend.hcl
# Edit the project and backend bucket; keep prefix=cicd (not invoice-platform).
terraform -chdir=infra/cicd init -backend-config=backend.hcl
terraform -chdir=infra/cicd plan
terraform -chdir=infra/cicd apply
terraform -chdir=infra/cicd output
```

Federation is restricted to this repository's immutable numeric IDs,
`refs/heads/main`, the `development` environment and this workflow's exact path.
The GitHub identity can submit builds and create releases, but cannot deploy to
Cloud Run directly. The builder can read staged source, write build logs and
push only to the application repository. The Cloud Deploy execution identity
can update the one service and migration job, invoke the job, read the release
image and run authenticated verification. None receives Terraform-state access,
direct Secret Manager access or an administrator role.

Add the **Cloud Deploy execution account**, not the GitHub deployer, to the
application environment's `invoker_members`. This permits both Cloud Run IAM
invocation and application-level authorization during verification. Keep the
canonical service URL in `api_token_audiences`, then apply `infra/terraform`.

```hcl
invoker_members = [
  "user:you@example.com",
  "serviceAccount:invoice-dev-deploy@YOUR_PROJECT.iam.gserviceaccount.com",
]
api_token_audiences = ["https://YOUR_SERVICE.run.app"]
```

Create a GitHub environment named `development`, restrict it to `main`, and add
these environment variables:

| Variable | Value |
|---|---|
| `GCP_PROJECT_ID` | Existing project ID |
| `GCP_REGION` | `europe-west2` |
| `GCP_SERVICE` | `invoice-dev-api` |
| `GCP_MIGRATION_JOB` | `invoice-dev-migrate` |
| `GCP_IMAGE_REPOSITORY` | `europe-west2-docker.pkg.dev/PROJECT/invoice-dev-images` |
| `GCP_SERVICE_URL` | `service_url` output of `infra/terraform` |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `workload_identity_provider` output of `infra/cicd` |
| `GCP_DEPLOYER_SERVICE_ACCOUNT` | `deployer_service_account` output of `infra/cicd` |
| `GCP_BUILD_SERVICE_ACCOUNT` | `build_service_account` output of `infra/cicd` |
| `GCP_BUILD_SOURCE_BUCKET` | `build_source_bucket` output of `infra/cicd` |
| `GCP_DELIVERY_PIPELINE` | `delivery_pipeline` output of `infra/cicd` |

Set `GCP_DEPLOY_ENABLED=true` as a **repository variable** last. Identifiers are
not secrets, so no service-account key or other GitHub secret is needed. Run the
workflow manually on `main` for the first release, then require the `ci` job in
branch protection.

## Ownership and recovery

Terraform creates the service and job and continues to own runtime configuration.
Release image fields are ignored so infrastructure plans do not redeploy an old
image. Each release snapshots the live Terraform-managed Cloud Run configuration
and changes only its image and Cloud Deploy traffic state. Do not apply the
application Terraform stack while a rollout is active.

For recovery, prefer Cloud Deploy's **Roll back** action to a previously
successful release. The pipeline retries failures once and normally performs
this automatically. If manual recovery is needed, select the last verified image
digest, update Cloud Run, route traffic to it, and investigate migration
compatibility separately; never reverse a database migration automatically.

See Google's documentation for [Cloud Run targets](https://docs.cloud.google.com/deploy/docs/run-targets),
[Cloud Run canaries](https://docs.cloud.google.com/deploy/docs/deployment-strategies/canary/cloud-run),
[deployment hooks](https://docs.cloud.google.com/deploy/docs/hooks), and
[rollout automation](https://docs.cloud.google.com/deploy/docs/automation-rules).
