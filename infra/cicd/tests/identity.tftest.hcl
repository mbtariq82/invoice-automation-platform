mock_provider "google" {}

override_resource {
  target          = google_service_account.builder
  override_during = plan
  values = {
    email = "invoice-dev-builder@invoice-test-project.iam.gserviceaccount.com"
    name  = "projects/invoice-test-project/serviceAccounts/invoice-dev-builder@invoice-test-project.iam.gserviceaccount.com"
  }
}

override_resource {
  target          = google_service_account.deploy_execution
  override_during = plan
  values = {
    email = "invoice-dev-deploy@invoice-test-project.iam.gserviceaccount.com"
    name  = "projects/invoice-test-project/serviceAccounts/invoice-dev-deploy@invoice-test-project.iam.gserviceaccount.com"
  }
}

variables {
  project_id           = "invoice-test-project"
  github_repository    = "example/invoices"
  github_repository_id = "1234"
  github_owner_id      = "5678"
}

run "restrict_deployment_identity" {
  command = plan
  assert {
    condition = alltrue([
      strcontains(google_iam_workload_identity_pool_provider.github.attribute_condition, "assertion.repository_id == '1234'"),
      strcontains(google_iam_workload_identity_pool_provider.github.attribute_condition, "assertion.repository_owner_id == '5678'"),
      strcontains(google_iam_workload_identity_pool_provider.github.attribute_condition, "refs/heads/main"),
      strcontains(google_iam_workload_identity_pool_provider.github.attribute_condition, "repo:example/invoices:environment:development"),
      strcontains(google_iam_workload_identity_pool_provider.github.attribute_condition, ".github/workflows/ci-cd.yml@refs/heads/main"),
    ])
    error_message = "Federation must restrict repository IDs, branch, environment and workflow."
  }
  assert {
    condition = (
      google_artifact_registry_repository_iam_member.publish.role == "roles/artifactregistry.writer" &&
      google_artifact_registry_repository_iam_member.publish.member == "serviceAccount:${google_service_account.builder.email}" &&
      google_project_iam_member.submit_builds.role == "roles/cloudbuild.builds.editor" &&
      google_project_iam_member.write_build_logs.role == "roles/logging.logWriter" &&
      google_cloud_run_v2_service_iam_member.deploy.role == "roles/run.developer" &&
      google_cloud_run_v2_service_iam_member.deploy.member == "serviceAccount:${google_service_account.deploy_execution.email}" &&
      google_service_account_iam_member.runtime_identity.role == "roles/iam.serviceAccountUser" &&
      google_project_iam_member.create_releases.role == "roles/clouddeploy.releaser" &&
      google_project_iam_member.deploy_job_runner.role == "roles/clouddeploy.jobRunner" &&
      google_project_iam_member.deploy_automation.role == "roles/clouddeploy.operator"
    )
    error_message = "Deployment must use resource-scoped grants."
  }
  assert {
    condition = (
      google_storage_bucket.build_source.public_access_prevention == "enforced" &&
      google_storage_bucket.build_source.uniform_bucket_level_access &&
      !google_storage_bucket.build_source.force_destroy
    )
    error_message = "Cloud Build source staging must remain private and deletion-safe."
  }
  assert {
    condition = (
      google_storage_bucket.deploy_artifacts.public_access_prevention == "enforced" &&
      google_storage_bucket.deploy_artifacts.uniform_bucket_level_access &&
      !google_storage_bucket.deploy_artifacts.force_destroy
    )
    error_message = "Cloud Deploy artifacts must remain private and deletion-safe for rollback."
  }
  assert {
    condition = (
      google_clouddeploy_target.development.execution_configs[0].service_account == google_service_account.deploy_execution.email &&
      google_clouddeploy_delivery_pipeline.api.serial_pipeline[0].stages[0].strategy[0].canary[0].canary_deployment[0].verify &&
      google_clouddeploy_delivery_pipeline.api.serial_pipeline[0].stages[0].strategy[0].canary[0].canary_deployment[0].percentages == tolist([10, 50]) &&
      google_clouddeploy_automation.api.service_account == google_service_account.deploy_execution.email
    )
    error_message = "Cloud Deploy must use the dedicated execution identity and verified progressive delivery."
  }
}
