mock_provider "google" {}

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
      google_cloud_run_v2_service_iam_member.deploy.role == "roles/run.developer" &&
      google_service_account_iam_member.runtime_identity.role == "roles/iam.serviceAccountUser"
    )
    error_message = "Deployment must use resource-scoped grants."
  }
}
