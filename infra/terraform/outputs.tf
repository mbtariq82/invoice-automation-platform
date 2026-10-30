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

output "gateway_service_account_email" {
  description = "Identity used by API Gateway to invoke the private API."
  value       = google_service_account.gateway.email
}

output "frontend_bucket_name" {
  description = "Public Cloud Storage bucket for the compiled React frontend."
  value       = try(google_storage_bucket.frontend[0].name, null)
}

output "frontend_url" {
  description = "Cloud Storage URL for the React frontend."
  value       = try("https://storage.googleapis.com/${google_storage_bucket.frontend[0].name}/index.html", null)
}

output "api_gateway_url" {
  description = "API Gateway hostname used by the React frontend."
  value       = try("https://${google_api_gateway_gateway.invoice[0].default_hostname}", null)
}
