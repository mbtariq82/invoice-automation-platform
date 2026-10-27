resource "google_artifact_registry_repository" "api" {
  project       = var.project_id
  location      = var.region
  repository_id = "${var.name_prefix}-images"
  description   = "Container images for the invoice API and migrations."
  format        = "DOCKER"
  labels        = local.labels

  depends_on = [google_project_service.required]
}
