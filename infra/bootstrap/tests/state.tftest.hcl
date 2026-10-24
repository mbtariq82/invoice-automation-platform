mock_provider "google" {}

run "private_versioned_state_bucket" {
  command = plan

  variables {
    project_id = "invoice-test-project"
  }

  assert {
    condition = (
      google_storage_bucket.terraform_state.uniform_bucket_level_access &&
      google_storage_bucket.terraform_state.public_access_prevention == "enforced" &&
      google_storage_bucket.terraform_state.versioning[0].enabled &&
      !google_storage_bucket.terraform_state.force_destroy
    )
    error_message = "State must be private, versioned, and protected from accidental bucket emptying."
  }
}

run "source_secrets_are_scoped_to_the_operator" {
  command = plan

  variables {
    project_id                = "invoice-test-project"
    credential_reader_members = ["user:operator@example.com"]
  }

  assert {
    condition = (
      google_project_service.secret_manager.disable_on_destroy == false &&
      google_secret_manager_secret.inputs["database_password"].secret_id == "invoice-dev-database-password" &&
      google_secret_manager_secret.inputs["openrouter_api_key"].secret_id == "invoice-dev-openrouter-source-key"
    )
    error_message = "Bootstrap must prepare the two source secrets before application planning."
  }

  assert {
    condition = length(google_secret_manager_secret_iam_member.credential_reader) == 2 && alltrue([
      for grant in google_secret_manager_secret_iam_member.credential_reader :
      grant.role == "roles/secretmanager.secretAccessor" && grant.member == "user:operator@example.com"
    ])
    error_message = "Only the specified operator should receive read access to the source secrets."
  }
}

run "reject_public_credential_access" {
  command = plan

  variables {
    project_id                = "invoice-test-project"
    credential_reader_members = ["allUsers"]
  }

  expect_failures = [var.credential_reader_members]
}
