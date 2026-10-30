# React frontend

The frontend is a React and TypeScript single-page application served by a
small Node.js process on Cloud Run. It supports Google sign-in, PDF upload,
invoice history, totals status and invoice detail review.

## Authentication path

The frontend Cloud Run service is public so a browser can load the sign-in
page. The API remains private. Browser API requests go to the same frontend
origin under `/api`; the Node proxy then sends two credentials upstream:

- `Authorization` contains a short-lived identity token for the dedicated
  frontend service account. Cloud Run IAM uses it to authorize the proxy.
- `X-API-Authorization` contains the signed Google ID token from the browser.
  FastAPI verifies it and uses its subject to enforce invoice ownership.

The proxy never converts an unsigned header into an identity and does not store
the user's token. The browser keeps the token in session storage, which is
cleared when that tab or browser session ends.

## Create the Google OAuth client

In **Google Cloud Console → Google Auth Platform**, configure the consent screen
and create a **Web application** OAuth client. The client ID is a public
identifier, not a secret. Add the final `frontend_url` Terraform output under
**Authorized JavaScript origins**. Google sign-in will not work from that origin
until it has been added.

Keep access restricted to your test users while the OAuth app is in testing.
The API additionally restricts callers through `invoker_members`.

## Local checks

Run these from PowerShell at the repository root:

```powershell
$pnpm = "C:\Users\mbtar\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd"
& $pnpm --dir frontend install --frozen-lockfile
& $pnpm --dir frontend test
& $pnpm --dir frontend build
docker build --platform linux/amd64 --tag invoice-frontend:local --file frontend/Dockerfile frontend
```

The frontend server needs Application Default Credentials when run outside
Cloud Run because it must mint an API identity token:

```powershell
gcloud auth application-default login
$env:API_BASE_URL = terraform -chdir=infra/terraform output -raw service_url
$env:GOOGLE_CLIENT_ID = "YOUR_CLIENT_ID.apps.googleusercontent.com"
& $pnpm --dir frontend start
```

Open `http://localhost:8080`. Add that origin to the OAuth client while doing
local development.

## Build and deploy to GCP

First apply the foundation with `deploy_frontend = false`. Build the frontend
using Cloud Build and capture its immutable digest:

```powershell
$projectId = "YOUR_PROJECT_ID"
$region = "europe-west2"
$imageRepository = terraform -chdir=infra/terraform output -raw image_repository
$imageTag = "$imageRepository/frontend:$(git rev-parse --short HEAD)"

gcloud builds submit . `
  --project=$projectId `
  --region=$region `
  --config=cloudbuild-frontend.yaml `
  --substitutions="_IMAGE=$imageTag"

$digest = gcloud artifacts docker images describe $imageTag `
  --project=$projectId `
  --format="value(image_summary.digest)"
$env:TF_VAR_frontend_container_image = "$imageRepository/frontend@$digest"
$env:TF_VAR_frontend_google_client_id = "YOUR_CLIENT_ID.apps.googleusercontent.com"
$env:TF_VAR_deploy_frontend = "true"
```

Add that same OAuth client ID to `api_token_audiences` and keep each permitted
user in `invoker_members` in the ignored environment variable file. Then review
and apply:

```powershell
terraform -chdir=infra/terraform plan -var-file=environments/dev.tfvars
terraform -chdir=infra/terraform apply -var-file=environments/dev.tfvars
terraform -chdir=infra/terraform output -raw frontend_url
```

After the first apply, add the returned HTTPS URL to the OAuth client's
Authorized JavaScript origins. Terraform creates:

- a dedicated `${name_prefix}-frontend` service account;
- a public Cloud Run frontend service;
- a narrowly scoped `roles/run.invoker` grant from that account to the API;
- runtime configuration containing the private API URL and public client ID.

No OAuth client secret is placed in Terraform, the container image or GitHub.
