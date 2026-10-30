# React frontend

The frontend is a React and TypeScript single-page application hosted in a
public Cloud Storage bucket. API requests go through API Gateway to the private
FastAPI Cloud Run service.

## Authentication path

API Gateway validates the browser's signed Google ID token, uses its dedicated
service account to invoke the private API, and routes requests to Cloud Run.
The browser keeps the token in session storage, which is cleared when that tab
or browser session ends.

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
$bun = "bun"
& $bun install --cwd frontend --frozen-lockfile
& $bun run test --cwd frontend
& $bun run --cwd frontend build
docker build --platform linux/amd64 --tag invoice-frontend:local --file frontend/Dockerfile frontend
```

The frontend server needs Application Default Credentials when run outside
Cloud Run because it must mint an API identity token:

```powershell
gcloud auth application-default login
$env:API_BASE_URL = terraform -chdir=infra/terraform output -raw service_url
$env:GOOGLE_CLIENT_ID = "YOUR_CLIENT_ID.apps.googleusercontent.com"
& $bun run --cwd frontend start
```

Open `http://localhost:8080`. Add that origin to the OAuth client while doing
local development.

## Build and deploy to GCP

First apply the foundation with `deploy_frontend = false`. Then enable the
static site and API Gateway:

```powershell
$projectId = "YOUR_PROJECT_ID"
$region = "europe-west2"
$env:TF_VAR_frontend_google_client_id = "YOUR_CLIENT_ID.apps.googleusercontent.com"
$env:TF_VAR_deploy_frontend = "true"
terraform -chdir=infra/terraform apply -var-file=environments/dev.tfvars

$bucket = terraform -chdir=infra/terraform output -raw frontend_bucket_name
& bun run --cwd frontend build
gcloud storage rsync frontend/dist "gs://$bucket" --recursive --delete-unmatched-destination-objects
```

Add that same OAuth client ID to `api_token_audiences` and keep each permitted
user in `invoker_members` in the ignored environment variable file. Then review
and apply:

```powershell
terraform -chdir=infra/terraform plan -var-file=environments/dev.tfvars
terraform -chdir=infra/terraform apply -var-file=environments/dev.tfvars
terraform -chdir=infra/terraform output -raw frontend_url
terraform -chdir=infra/terraform output -raw api_gateway_url
```

After the first apply, add the returned HTTPS URL to the OAuth client's
Authorized JavaScript origins. Terraform creates:

- a dedicated `${name_prefix}-frontend` service account;
- a public Cloud Run frontend service;
- a narrowly scoped `roles/run.invoker` grant from that account to the API;
- runtime configuration containing the private API URL and public client ID.

No OAuth client secret is placed in Terraform, the container image or GitHub.
