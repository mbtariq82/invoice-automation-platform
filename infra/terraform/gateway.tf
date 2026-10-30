resource "google_storage_bucket" "frontend" {
  count                       = var.deploy_frontend ? 1 : 0
  project                     = var.project_id
  name                        = "${var.project_id}-${var.name_prefix}-frontend"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "inherited"
  force_destroy               = false
  labels                      = local.labels
}

resource "google_storage_bucket_iam_member" "frontend_public" {
  count  = var.deploy_frontend ? 1 : 0
  bucket = google_storage_bucket.frontend[0].name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

resource "google_api_gateway_api" "invoice" {
  count    = var.deploy_frontend ? 1 : 0
  provider = google
  project  = var.project_id
  api_id   = "${var.name_prefix}-api"
  labels   = local.labels
}

resource "google_api_gateway_api_config" "invoice" {
  count         = var.deploy_frontend ? 1 : 0
  project       = var.project_id
  api           = google_api_gateway_api.invoice[0].api_id
  api_config_id = "${var.name_prefix}-api-config-${substr(md5(google_cloud_run_v2_service.api[0].uri), 0, 8)}"

  openapi_documents {
    document {
      path = "openapi.yaml"
      contents = base64encode(templatefile("${path.module}/openapi.yaml.tftpl", {
        api_url         = google_cloud_run_v2_service.api[0].uri
        gateway_host    = "${var.name_prefix}-api-${var.project_id}.gateway.dev"
        name_prefix     = var.name_prefix
        oauth_client_id = var.frontend_google_client_id
      }))
    }
  }

  gateway_config {
    backend_config {
      google_service_account = google_service_account.gateway.email
    }
  }
}

resource "google_api_gateway_gateway" "invoice" {
  count      = var.deploy_frontend ? 1 : 0
  project    = var.project_id
  region     = var.region
  api        = google_api_gateway_api.invoice[0].api_id
  gateway_id = "${var.name_prefix}-gateway"
  labels     = local.labels
  api_config = google_api_gateway_api_config.invoice[0].id
}

resource "google_cloud_run_v2_service_iam_member" "gateway_api_invoker" {
  count    = var.deploy_frontend ? 1 : 0
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api[0].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.gateway.email}"
}

resource "google_storage_bucket_object" "frontend_config" {
  count        = var.deploy_frontend ? 1 : 0
  name         = "config.js"
  bucket       = google_storage_bucket.frontend[0].name
  content_type = "application/javascript"
  content      = <<-EOF
    window.__APP_CONFIG__ = {
      googleClientId: ${jsonencode(var.frontend_google_client_id)},
      apiBaseUrl: ${jsonencode("https://${google_api_gateway_gateway.invoice[0].default_hostname}")}
    };
  EOF
}
