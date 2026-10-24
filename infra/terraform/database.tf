module "credential_inputs" {
  source = "./modules/credential_inputs"

  providers = {
    google = google.secret_source
  }

  project_id                   = var.project_id
  name_prefix                  = var.name_prefix
  database_credentials_version = var.database_credentials_version
  openrouter_key_version       = var.openrouter_key_version
}

resource "google_sql_database_instance" "postgres" {
  project             = var.project_id
  name                = "${var.name_prefix}-postgres"
  database_version    = "POSTGRES_17"
  region              = var.region
  deletion_protection = var.deletion_protection

  settings {
    edition                     = "ENTERPRISE"
    tier                        = "db-f1-micro"
    availability_type           = "ZONAL"
    disk_type                   = "PD_SSD"
    disk_size                   = 10
    disk_autoresize             = true
    disk_autoresize_limit       = 20
    deletion_protection_enabled = var.deletion_protection
    connector_enforcement       = "REQUIRED"
    user_labels                 = local.labels

    ip_configuration {
      ipv4_enabled = true
      ssl_mode     = "ENCRYPTED_ONLY"
      # No authorized networks: clients must use an authenticated connector.
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "02:00"
      transaction_log_retention_days = 7

      backup_retention_settings {
        retained_backups = 7
      }
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_sql_database" "invoices" {
  project  = var.project_id
  name     = "invoices"
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "application" {
  project             = var.project_id
  instance            = google_sql_database_instance.postgres.name
  name                = "invoice_app"
  password_wo         = module.credential_inputs.database_password
  password_wo_version = var.database_credentials_version
  # This user owns migrated tables; removing it directly can block teardown.
  deletion_policy = "ABANDON"
}

resource "google_secret_manager_secret" "database_url" {
  project   = var.project_id
  secret_id = "${var.name_prefix}-database-url"
  labels    = local.labels

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_version" "database_url" {
  secret                 = google_secret_manager_secret.database_url.id
  secret_data_wo         = "postgresql+psycopg://${google_sql_user.application.name}:${replace(urlencode(module.credential_inputs.database_password), "+", "%20")}@/${google_sql_database.invoices.name}?host=/cloudsql/${google_sql_database_instance.postgres.connection_name}"
  secret_data_wo_version = tostring(var.database_credentials_version)
  deletion_policy        = "ABANDON"

  lifecycle {
    create_before_destroy = true
  }
}

resource "google_secret_manager_secret" "openrouter_api_key" {
  project   = var.project_id
  secret_id = "${var.name_prefix}-openrouter-api-key"
  labels    = local.labels

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_version" "openrouter_api_key" {
  secret                 = google_secret_manager_secret.openrouter_api_key.id
  secret_data_wo         = module.credential_inputs.openrouter_api_key
  secret_data_wo_version = tostring(var.openrouter_key_version)
  deletion_policy        = "ABANDON"

  lifecycle {
    create_before_destroy = true
  }
}

resource "google_secret_manager_secret_iam_member" "database_access" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.database_url.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_secret_manager_secret_iam_member" "model_access" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.openrouter_api_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}
