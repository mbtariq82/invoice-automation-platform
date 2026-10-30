output "image_repository" {
  description = "Push the API image under this Artifact Registry repository."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.api.repository_id}"
}

output "invoice_bucket_name" {
  description = "Private bucket reserved for original invoice PDFs."
  value       = google_storage_bucket.invoices.name
}

output "runtime_service_account_email" {
  description = "Identity used by the API and migration job."
  value       = google_service_account.runtime.email
}

output "database_connection_name" {
  description = "Cloud SQL connection name mounted under /cloudsql."
  value       = google_sql_database_instance.postgres.connection_name
}

output "service_url" {
  description = "Authenticated API URL; null until deploy_application is enabled."
  value       = try(google_cloud_run_v2_service.api[0].uri, null)
}

output "migration_job_name" {
  description = "Execute this job before using invoice endpoints."
  value       = try(google_cloud_run_v2_job.migrate[0].name, null)
}

output "frontend_service_account_email" {
  description = "Identity used by the frontend to invoke the private API."
  value       = google_service_account.frontend.email
}

output "frontend_url" {
  description = "Public React frontend URL; null until deploy_frontend is enabled."
  value       = try(google_cloud_run_v2_service.frontend[0].uri, null)
}
