# Frontend implementation command log

These are the PowerShell commands used to create, validate and package the
frontend change in this PR. Values such as the project ID and OAuth client ID
are placeholders in the deployment guide; no credentials are included.

```powershell
git fetch origin main
git switch main
git pull --ff-only origin main
git switch -c codex/react-frontend
node --version
gh api repos/actions/setup-node/git/ref/tags/v6 --jq .object.sha
gh api repos/oven-sh/setup-bun/git/ref/tags/v2 --jq .object.sha

& bun install --cwd frontend --frozen-lockfile
& bun run test --cwd frontend
& bun run --cwd frontend build
& bun install --cwd frontend --frozen-lockfile
& bun run test --cwd frontend
& bun run --cwd frontend build

& "$env:TEMP\invoice-terraform-tools-1.14.0\terraform.exe" fmt -recursive infra
$env:GOOGLE_OAUTH_ACCESS_TOKEN = "offline-test-token"
$env:TF_DATA_DIR = "$env:TEMP\invoice-tf-frontend"
& "$env:TEMP\invoice-terraform-tools-1.14.0\terraform.exe" -chdir=infra/terraform init -backend=false -input=false
& "$env:TEMP\invoice-terraform-tools-1.14.0\terraform.exe" -chdir=infra/terraform validate
& "$env:TEMP\invoice-terraform-tools-1.14.0\terraform.exe" -chdir=infra/terraform test

node --check frontend/server.mjs
& bun audit --cwd frontend --production
docker build --platform linux/amd64 --tag invoice-frontend:ci --file frontend/Dockerfile frontend
docker run --detach --publish 18080:8080 --env API_BASE_URL=https://example.run.app --env GOOGLE_CLIENT_ID=123-example.apps.googleusercontent.com invoice-frontend:ci
docker logs <container-id>
docker inspect <container-id> --format '{{.State.Status}} {{.State.ExitCode}}'
docker rm --force <container-id>
docker run --detach --name invoice-frontend-preview --publish 18080:8080 --env API_BASE_URL=https://example.run.app --env GOOGLE_CLIENT_ID=123-example.apps.googleusercontent invoice-frontend:ci
docker rm --force invoice-frontend-preview

uv run --locked pytest -q
& bun run test --cwd frontend
& bun run --cwd frontend build
& "$env:TEMP\invoice-actionlint-1.7.12\actionlint.exe" .github/workflows/ci-cd.yml
git diff --check
git status --short --branch
git add .github/workflows/ci-cd.yml README.md infra/README.md infra/terraform cloudbuild-frontend.yaml docs/frontend.md docs/frontend-command-log.md frontend tests/test_deploy.py
git commit -m "Add React frontend and Cloud Run infrastructure"
git push origin codex/react-frontend
```

The all-stack CI command used by GitHub is equivalent to:

```powershell
$terraform = "$env:TEMP\invoice-terraform-tools-1.14.0\terraform.exe"
$env:GOOGLE_OAUTH_ACCESS_TOKEN = "offline-test-token"
foreach ($stack in @("bootstrap", "terraform", "cicd")) {
  $env:TF_DATA_DIR = "$env:TEMP\invoice-frontend-$stack"
  & $terraform "-chdir=infra/$stack" init -backend=false -input=false
  & $terraform "-chdir=infra/$stack" validate
  & $terraform "-chdir=infra/$stack" test
}
```
