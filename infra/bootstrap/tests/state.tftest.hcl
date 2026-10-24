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
