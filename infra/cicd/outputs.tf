output "workload_identity_provider" {
  value = google_iam_workload_identity_pool_provider.github.name
}

output "deployer_service_account" {
  value = google_service_account.deployer.email
}

output "build_service_account" {
  value = google_service_account.builder.email
}

output "build_source_bucket" {
  value = "gs://${google_storage_bucket.build_source.name}"
}

output "deploy_execution_service_account" {
  value = google_service_account.deploy_execution.email
}

output "delivery_pipeline" {
  value = google_clouddeploy_delivery_pipeline.api.name
}
