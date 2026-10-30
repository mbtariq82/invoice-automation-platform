resource "google_cloud_run_v2_service" "api" {
  count = var.deploy_application ? 1 : 0

  project             = var.project_id
  name                = "${var.name_prefix}-api"
  location            = var.region
  deletion_protection = var.deletion_protection
  ingress             = "INGRESS_TRAFFIC_ALL"
  labels              = local.labels

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  scaling {
    min_instance_count = 1
    max_instance_count = 1
  }

  template {
    service_account                  = google_service_account.runtime.email
    execution_environment            = "EXECUTION_ENVIRONMENT_GEN2"
    max_instance_request_concurrency = 2
    timeout                          = "180s"

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.postgres.connection_name]
      }
    }

    containers {
      image = var.container_image

      ports {
        container_port = 8000
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      env {
        name  = "DATABASE_URL_SECRET_VERSION"
        value = "${google_secret_manager_secret.database_url.id}/versions/${google_secret_manager_secret_version.database_url.version}"
      }

      env {
        name  = "OPENROUTER_API_KEY_SECRET_VERSION"
        value = "${google_secret_manager_secret.openrouter_api_key.id}/versions/${google_secret_manager_secret_version.openrouter_api_key.version}"
      }

      env {
        name  = "OPENROUTER_MODEL"
        value = var.openrouter_model
      }

      env {
        name  = "INVOICE_BUCKET"
        value = google_storage_bucket.invoices.name
      }

      env {
        name  = "API_ADMIN_SUBJECTS"
        value = join(",", var.admin_members)
      }

      env {
        name  = "API_TOKEN_AUDIENCES"
        value = join(",", sort(tolist(var.api_token_audiences)))
      }

      env {
        name  = "API_ALLOWED_MEMBERS"
        value = join(",", sort(tolist(var.invoker_members)))
      }

      startup_probe {
        http_get {
          path = "/health"
          port = 8000
        }
        period_seconds    = 5
        timeout_seconds   = 2
        failure_threshold = 12
      }
    }
  }

  lifecycle {
    # CI/CD owns releases; infrastructure applies must not redeploy an old image.
    ignore_changes = [template[0].containers[0].image]

    precondition {
      condition     = var.container_image != "" && trimspace(var.openrouter_model) != ""
      error_message = "Set container_image and openrouter_model before enabling deploy_application."
    }

    precondition {
      condition     = length(var.api_token_audiences) > 0 && length(var.invoker_members) > 0
      error_message = "Set api_token_audiences and invoker_members before enabling deploy_application."
    }
  }

  depends_on = [
    google_project_iam_member.cloud_sql_client,
    google_secret_manager_secret_iam_member.database_access,
    google_secret_manager_secret_iam_member.model_access,
    google_storage_bucket_iam_member.invoice_access,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "invoker" {
  for_each = var.deploy_application ? var.invoker_members : toset([])

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api[0].name
  role     = "roles/run.invoker"
  member   = each.value
}

resource "google_cloud_run_v2_service" "frontend" {
  count = var.deploy_frontend ? 1 : 0

  project             = var.project_id
  name                = "${var.name_prefix}-frontend"
  location            = var.region
  deletion_protection = var.deletion_protection
  ingress             = "INGRESS_TRAFFIC_ALL"
  labels              = local.labels

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  scaling {
    min_instance_count = 0
    max_instance_count = 2
  }

  template {
    service_account                  = google_service_account.frontend.email
    execution_environment            = "EXECUTION_ENVIRONMENT_GEN2"
    max_instance_request_concurrency = 80
    timeout                          = "60s"

    containers {
      image = var.frontend_container_image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      env {
        name  = "API_BASE_URL"
        value = google_cloud_run_v2_service.api[0].uri
      }

      env {
        name  = "GOOGLE_CLIENT_ID"
        value = var.frontend_google_client_id
      }

      startup_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        period_seconds    = 5
        timeout_seconds   = 2
        failure_threshold = 12
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image]

    precondition {
      condition     = var.deploy_application && var.frontend_container_image != "" && var.frontend_google_client_id != ""
      error_message = "Deploy the API and set frontend_container_image and frontend_google_client_id before enabling deploy_frontend."
    }

    precondition {
      condition     = contains(var.api_token_audiences, var.frontend_google_client_id)
      error_message = "Add frontend_google_client_id to api_token_audiences so the API accepts signed user tokens."
    }
  }

  depends_on = [google_cloud_run_v2_service_iam_member.frontend_api_invoker]
}

resource "google_cloud_run_v2_service_iam_member" "frontend_api_invoker" {
  count = var.deploy_frontend ? 1 : 0

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api[0].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.frontend.email}"
}

resource "google_cloud_run_v2_service_iam_member" "public_frontend" {
  count = var.deploy_frontend ? 1 : 0

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.frontend[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_job" "migrate" {
  count = var.deploy_application ? 1 : 0

  project             = var.project_id
  name                = "${var.name_prefix}-migrate"
  location            = var.region
  deletion_protection = var.deletion_protection
  labels              = local.labels

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image]
  }

  template {
    task_count  = 1
    parallelism = 1

    template {
      service_account = google_service_account.runtime.email
      timeout         = "300s"
      max_retries     = 0

      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.postgres.connection_name]
        }
      }

      containers {
        image   = var.container_image
        command = ["alembic"]
        args    = ["upgrade", "head"]

        resources {
          limits = {
            cpu    = "1"
            memory = "512Mi"
          }
        }

        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }

        env {
          name  = "DATABASE_URL_SECRET_VERSION"
          value = "${google_secret_manager_secret.database_url.id}/versions/${google_secret_manager_secret_version.database_url.version}"
        }
      }
    }
  }

  depends_on = [
    google_project_iam_member.cloud_sql_client,
    google_secret_manager_secret_iam_member.database_access,
  ]
}
