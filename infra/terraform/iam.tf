resource "google_service_account" "runtime" {
  project      = var.project_id
  account_id   = "${var.name_prefix}-runtime"
  display_name = "Invoice application runtime"

  depends_on = [google_project_service.required]
}

resource "google_service_account" "gateway" {
  project      = var.project_id
  account_id   = "${var.name_prefix}-gateway"
  display_name = "Invoice API Gateway"

  depends_on = [google_project_service.required]
}

resource "google_project_iam_member" "cloud_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_project_iam_member" "vertex_ai_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}
