resource "google_project_service" "federation" {
  for_each = toset([
    "cloudbuild.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "logging.googleapis.com",
    "sts.googleapis.com",
  ])
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_service_account" "deployer" {
  project      = var.project_id
  account_id   = "${var.name_prefix}-deployer"
  display_name = "GitHub development releases"
  depends_on   = [google_project_service.federation]
}

resource "google_service_account" "builder" {
  project      = var.project_id
  account_id   = "${var.name_prefix}-builder"
  display_name = "Cloud Build container builds"
  depends_on   = [google_project_service.federation]
}

resource "google_storage_bucket" "build_source" {
  project                     = var.project_id
  name                        = "${var.project_id}-${var.name_prefix}-build-source"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  lifecycle_rule {
    condition {
      age = 7
    }
    action {
      type = "Delete"
    }
  }
}

resource "google_iam_workload_identity_pool" "github" {
  project                   = var.project_id
  workload_identity_pool_id = "${var.name_prefix}-github"
  display_name              = "Invoice GitHub Actions"
  depends_on                = [google_project_service.federation]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  attribute_mapping = {
    "google.subject"                = "assertion.sub"
    "attribute.repository_id"       = "assertion.repository_id"
    "attribute.repository_owner_id" = "assertion.repository_owner_id"
    "attribute.ref"                 = "assertion.ref"
    "attribute.workflow_ref"        = "assertion.workflow_ref"
  }
  attribute_condition = join(" && ", [
    "assertion.repository_id == '${var.github_repository_id}'",
    "assertion.repository_owner_id == '${var.github_owner_id}'",
    "assertion.ref == 'refs/heads/main'",
    "assertion.sub == 'repo:${var.github_repository}:environment:development'",
    "assertion.workflow_ref == '${var.github_repository}/.github/workflows/ci-cd.yml@refs/heads/main'",
  ])
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_impersonation" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository_id/${var.github_repository_id}"
}

resource "google_artifact_registry_repository_iam_member" "publish" {
  project    = var.project_id
  location   = var.region
  repository = "${var.name_prefix}-images"
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.builder.email}"
}

resource "google_project_iam_member" "submit_builds" {
  project = var.project_id
  role    = "roles/cloudbuild.builds.editor"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_project_iam_member" "write_build_logs" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.builder.email}"
}

resource "google_service_account_iam_member" "use_builder" {
  service_account_id = google_service_account.builder.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_storage_bucket_iam_member" "stage_source" {
  for_each = toset(["roles/storage.bucketViewer", "roles/storage.objectUser"])
  bucket   = google_storage_bucket.build_source.name
  role     = each.value
  member   = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_storage_bucket_iam_member" "read_source" {
  for_each = toset(["roles/storage.bucketViewer", "roles/storage.objectViewer"])
  bucket   = google_storage_bucket.build_source.name
  role     = each.value
  member   = "serviceAccount:${google_service_account.builder.email}"
}

resource "google_service_account_iam_member" "runtime_identity" {
  service_account_id = "projects/${var.project_id}/serviceAccounts/${var.name_prefix}-runtime@${var.project_id}.iam.gserviceaccount.com"
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_cloud_run_v2_service_iam_member" "deploy" {
  project  = var.project_id
  location = var.region
  name     = "${var.name_prefix}-api"
  role     = "roles/run.developer"
  member   = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_cloud_run_v2_job_iam_member" "migrate" {
  for_each = toset(["roles/run.developer", "roles/run.invoker"])
  project  = var.project_id
  location = var.region
  name     = "${var.name_prefix}-migrate"
  role     = each.value
  member   = "serviceAccount:${google_service_account.deployer.email}"
}
