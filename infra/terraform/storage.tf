resource "google_storage_bucket" "invoices" {
  project                     = var.project_id
  name                        = "${var.project_id}-${var.name_prefix}-pdfs"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  labels                      = local.labels

  depends_on = [google_project_service.required]
}

resource "google_storage_bucket_iam_member" "invoice_access" {
  for_each = toset(["roles/storage.objectCreator", "roles/storage.objectViewer"])

  bucket = google_storage_bucket.invoices.name
  role   = each.value
  member = "serviceAccount:${google_service_account.runtime.email}"
}
