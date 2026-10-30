mock_provider "google" {
  override_during = plan

  mock_resource "google_secret_manager_secret_version" {
    defaults = {
      version = "7"
    }
  }
}

override_resource {
  target          = google_secret_manager_secret.database_url
  override_during = plan
  values = {
    id = "projects/invoice-test-project/secrets/invoice-dev-database-url"
  }
}

override_resource {
  target          = google_secret_manager_secret.openrouter_api_key
  override_during = plan
  values = {
    id = "projects/invoice-test-project/secrets/invoice-dev-openrouter-api-key"
  }
}

override_resource {
  target          = google_service_account.gateway
  override_during = plan
  values = {
    email = "invoice-dev-frontend@invoice-test-project.iam.gserviceaccount.com"
  }
}

override_resource {
  target          = google_cloud_run_v2_service.api
  override_during = plan
  values = {
    uri = "https://invoice-test.run.app"
  }
}

override_module {
  target = module.credential_inputs
  outputs = {
    database_password  = "offline-test-password"
    openrouter_api_key = "offline-test-key"
  }
}

variables {
  project_id         = "invoice-test-project"
  deploy_application = false
  container_image    = ""
  openrouter_model   = ""
  invoker_members    = []
}

run "foundation_without_an_application_image" {
  command = plan

  assert {
    condition     = length(google_cloud_run_v2_service.api) == 0 && length(google_cloud_run_v2_job.migrate) == 0
    error_message = "Foundation provisioning must work before an application image exists."
  }

  assert {
    condition = (
      google_storage_bucket.invoices.uniform_bucket_level_access &&
      google_storage_bucket.invoices.public_access_prevention == "enforced" &&
      !google_storage_bucket.invoices.force_destroy
    )
    error_message = "Invoice PDFs must stay private and non-empty buckets must resist deletion."
  }

  assert {
    condition = toset([for grant in google_storage_bucket_iam_member.invoice_access : grant.role]) == toset([
      "roles/storage.objectCreator", "roles/storage.objectViewer"
    ])
    error_message = "The application needs to create and read PDFs without deleting them."
  }

  assert {
    condition = (
      google_sql_database_instance.postgres.deletion_protection &&
      google_sql_database_instance.postgres.settings[0].connector_enforcement == "REQUIRED" &&
      google_sql_database_instance.postgres.settings[0].ip_configuration[0].ssl_mode == "ENCRYPTED_ONLY" &&
      length(google_sql_database_instance.postgres.settings[0].ip_configuration[0].authorized_networks) == 0
    )
    error_message = "The database must require encrypted connector access and deletion protection."
  }

  assert {
    condition = (
      google_sql_user.application.password == null &&
      google_secret_manager_secret_version.database_url.secret_data == null &&
      google_secret_manager_secret_version.openrouter_api_key.secret_data == null
    )
    error_message = "Credentials must use write-only attributes, not state-backed password/secret_data."
  }
}

run "application_uses_the_database_bucket_and_pinned_secrets" {
  command = plan

  variables {
    deploy_application  = true
    container_image     = "europe-west2-docker.pkg.dev/invoice-test-project/invoice-dev-images/api@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    openrouter_model    = "offline-model"
    invoker_members     = ["user:developer@example.com"]
    api_token_audiences = ["https://invoice-test.run.app"]
  }

  assert {
    condition = (
      google_cloud_run_v2_service.api[0].scaling[0].min_instance_count == 1 &&
      google_cloud_run_v2_service.api[0].scaling[0].max_instance_count == 1 &&
      google_cloud_run_v2_service.api[0].template[0].max_instance_request_concurrency == 2
    )
    error_message = "The development API must scale conservatively for the small database."
  }

  assert {
    condition = one([
      for env in google_cloud_run_v2_service.api[0].template[0].containers[0].env : env.value
      if env.name == "INVOICE_BUCKET"
    ]) == google_storage_bucket.invoices.name
    error_message = "The application must receive its configured invoice bucket."
  }

  assert {
    condition = length([
      for env in google_cloud_run_v2_service.api[0].template[0].containers[0].env : env.name
      if contains(["DATABASE_URL_SECRET_VERSION", "OPENROUTER_API_KEY_SECRET_VERSION"], env.name)
      ]) == 2 && alltrue([
      for env in google_cloud_run_v2_service.api[0].template[0].containers[0].env :
      endswith(env.value, "/versions/7") && length(env.value_source) == 0
      if contains(["DATABASE_URL_SECRET_VERSION", "OPENROUTER_API_KEY_SECRET_VERSION"], env.name)
    ])
    error_message = "Use actual Secret Manager versions, not latest or the credential update counters."
  }

  assert {
    condition = (
      google_cloud_run_v2_job.migrate[0].template[0].task_count == 1 &&
      google_cloud_run_v2_job.migrate[0].template[0].template[0].max_retries == 0 &&
      one(google_cloud_run_v2_job.migrate[0].template[0].template[0].containers[0].command) == "alembic" &&
      toset([for env in google_cloud_run_v2_job.migrate[0].template[0].template[0].containers[0].env : env.name]) == toset(["DATABASE_URL_SECRET_VERSION"])
    )
    error_message = "Migrations must run once with database configuration only."
  }

  assert {
    condition     = length(google_cloud_run_v2_service_iam_member.invoker) == 1
    error_message = "Grant only the configured caller access to the private API."
  }
}

run "frontend_uses_storage_and_api_gateway" {
  command = plan

  variables {
    deploy_application        = true
    container_image           = "europe-west2-docker.pkg.dev/invoice-test-project/invoice-dev-images/api@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    openrouter_model          = "offline-model"
    invoker_members           = ["user:developer@example.com"]
    deploy_frontend           = true
    frontend_google_client_id = "123456789-example.apps.googleusercontent.com"
    api_token_audiences       = ["123456789-example.apps.googleusercontent.com"]
  }

  assert {
    condition = (
      google_storage_bucket.frontend[0].uniform_bucket_level_access &&
      google_storage_bucket_iam_member.frontend_public[0].member == "allUsers" &&
      google_cloud_run_v2_service_iam_member.gateway_api_invoker[0].member == "serviceAccount:${google_service_account.gateway.email}"
    )
    error_message = "The frontend bucket must be public and API Gateway must use its dedicated identity."
  }

  assert {
    condition     = google_storage_bucket_object.frontend_config[0].content_type == "application/javascript"
    error_message = "The static frontend must receive runtime API and OAuth configuration."
  }
}

run "reject_missing_image_and_model" {
  command = plan

  variables {
    deploy_application = true
  }

  expect_failures = [google_cloud_run_v2_service.api[0]]
}

run "reject_mutable_image_tags" {
  command = plan

  variables {
    container_image = "europe-west2-docker.pkg.dev/invoice-test-project/invoice-dev-images/api:latest"
  }

  expect_failures = [var.container_image]
}

run "reject_public_api_access" {
  command = plan

  variables {
    invoker_members = ["allUsers"]
  }

  expect_failures = [var.invoker_members]
}

run "reject_invalid_source_secret_version" {
  command = plan

  variables {
    database_credentials_version = 0
  }

  expect_failures = [var.database_credentials_version]
}
