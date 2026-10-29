resource "google_project_service" "federation" {
  for_each = toset([
    "cloudbuild.googleapis.com",
    "clouddeploy.googleapis.com",
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

resource "google_service_account" "deploy_execution" {
  project      = var.project_id
  account_id   = "${var.name_prefix}-deploy"
  display_name = "Cloud Deploy execution and automation"
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

resource "google_storage_bucket" "deploy_artifacts" {
  project                     = var.project_id
  name                        = "${var.project_id}-${var.name_prefix}-deploy-artifacts"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
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

resource "google_artifact_registry_repository_iam_member" "deploy_read" {
  project    = var.project_id
  location   = var.region
  repository = "${var.name_prefix}-images"
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.deploy_execution.email}"
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

resource "google_project_iam_member" "create_releases" {
  project = var.project_id
  role    = "roles/clouddeploy.releaser"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_service_account_iam_member" "use_deploy_execution" {
  service_account_id = google_service_account.deploy_execution.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_service_account_iam_member" "automation_uses_deploy_execution" {
  service_account_id = google_service_account.deploy_execution.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deploy_execution.email}"
}

resource "google_project_iam_member" "deploy_job_runner" {
  project = var.project_id
  role    = "roles/clouddeploy.jobRunner"
  member  = "serviceAccount:${google_service_account.deploy_execution.email}"
}

resource "google_project_iam_member" "deploy_automation" {
  project = var.project_id
  role    = "roles/clouddeploy.operator"
  member  = "serviceAccount:${google_service_account.deploy_execution.email}"
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
  member             = "serviceAccount:${google_service_account.deploy_execution.email}"
}

resource "google_cloud_run_v2_service_iam_member" "deploy" {
  project  = var.project_id
  location = var.region
  name     = "${var.name_prefix}-api"
  role     = "roles/run.developer"
  member   = "serviceAccount:${google_service_account.deploy_execution.email}"
}

resource "google_cloud_run_v2_job_iam_member" "migrate" {
  for_each = toset(["roles/run.developer", "roles/run.invoker"])
  project  = var.project_id
  location = var.region
  name     = "${var.name_prefix}-migrate"
  role     = each.value
  member   = "serviceAccount:${google_service_account.deploy_execution.email}"
}

locals {
  cloud_sdk_image = "gcr.io/google.com/cloudsdktool/google-cloud-cli@sha256:2a5368c4f3e25f7e202ccbd7b63e4128380d8fd683266f7f015c5d0afcc8f3be"
}

resource "google_clouddeploy_target" "development" {
  project          = var.project_id
  location         = var.region
  name             = "${var.name_prefix}-api"
  description      = "Invoice API development Cloud Run service"
  require_approval = false

  run {
    location = "projects/${var.project_id}/locations/${var.region}"
  }

  execution_configs {
    usages            = ["RENDER", "DEPLOY", "PREDEPLOY", "VERIFY"]
    service_account   = google_service_account.deploy_execution.email
    artifact_storage  = "gs://${google_storage_bucket.deploy_artifacts.name}"
    execution_timeout = "1800s"
    default_pool {}
  }

  depends_on = [google_project_iam_member.deploy_job_runner]
}

resource "google_clouddeploy_delivery_pipeline" "api" {
  project     = var.project_id
  location    = var.region
  name        = "${var.name_prefix}-api"
  description = "Build-once, progressive delivery for the invoice API"

  serial_pipeline {
    stages {
      target_id = google_clouddeploy_target.development.name
      profiles  = []

      strategy {
        canary {
          runtime_config {
            cloud_run {
              automatic_traffic_control = true
              canary_revision_tags      = ["candidate"]
              prior_revision_tags       = ["previous"]
              stable_revision_tags      = ["stable"]
            }
          }

          canary_deployment {
            percentages = [10, 50]
            verify      = true

            predeploy {
              actions = ["migrate"]
            }

            verify_config {
              tasks {
                container {
                  image   = local.cloud_sdk_image
                  command = ["/bin/bash"]
                  args = ["-ceu", <<-EOT
                    REVISION_URL=$(gcloud run services describe "$CLOUD_RUN_SERVICE" \
                      --project="$CLOUD_RUN_PROJECT" \
                      --region="$CLOUD_RUN_LOCATION" --format=json | \
                      python3 -c 'import json, os, sys; data=json.load(sys.stdin); print(next(item["url"] for item in data["status"]["traffic"] if item.get("revisionName") == os.environ["REVISION"]))')
                    TOKEN=$(gcloud auth print-identity-token \
                      --audiences="$SERVICE_URL" --include-email)
                    export REVISION_URL TOKEN
                    python3 - <<'PY'
                    import json
                    import os
                    from urllib.request import Request, urlopen

                    headers = {
                        "Authorization": "Bearer " + os.environ["TOKEN"],
                        "X-API-Authorization": "Bearer " + os.environ["TOKEN"],
                    }
                    for path in ("/health", "/v1/invoices"):
                        with urlopen(Request(os.environ["REVISION_URL"] + path, headers=headers), timeout=30) as response:
                            body = json.load(response)
                            if response.status != 200:
                                raise RuntimeError(f"{path} returned {response.status}")
                            if path == "/health" and body != {"status": "ok"}:
                                raise RuntimeError("health response was not ready")
                            if path == "/v1/invoices" and not isinstance(body, list):
                                raise RuntimeError("invoice response was not a list")
                    PY
                  EOT
                  ]
                  env = {
                    REVISION    = "$${{ render.metadata.cloud_run.revision.id }}"
                    SERVICE_URL = "$${{ rollout.metadata.cloud_run.service.url }}"
                  }
                }
              }
            }
          }
        }
      }
    }
  }

  depends_on = [google_project_service.federation]
}

resource "google_clouddeploy_automation" "api" {
  project           = var.project_id
  location          = var.region
  name              = "${var.name_prefix}-api-release"
  delivery_pipeline = google_clouddeploy_delivery_pipeline.api.name
  service_account   = google_service_account.deploy_execution.email
  description       = "Advance verified canaries; retry and roll back failures"

  selector {
    targets {
      id = google_clouddeploy_target.development.name
    }
  }

  rules {
    advance_rollout_rule {
      id            = "advance-verified-canary"
      source_phases = ["canary-10", "canary-50"]
    }
  }

  rules {
    repair_rollout_rule {
      id = "repair-or-rollback"
      repair_phases {
        retry {
          attempts     = 1
          wait         = "30s"
          backoff_mode = "BACKOFF_MODE_LINEAR"
        }
      }
      repair_phases {
        rollback {
          destination_phase                   = "stable"
          disable_rollback_if_rollout_pending = true
        }
      }
    }
  }

  depends_on = [
    google_project_iam_member.deploy_automation,
    google_service_account_iam_member.automation_uses_deploy_execution,
  ]
}
