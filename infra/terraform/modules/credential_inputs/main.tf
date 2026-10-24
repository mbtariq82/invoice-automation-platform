terraform {
  required_providers {
    google = {
      source = "hashicorp/google"
    }
  }
}

variable "project_id" {
  type = string
}

variable "name_prefix" {
  type = string
}

variable "database_credentials_version" {
  type = number
}

variable "openrouter_key_version" {
  type = number
}

ephemeral "google_secret_manager_secret_version" "database_password" {
  project = var.project_id
  secret  = "${var.name_prefix}-database-password"
  version = tostring(var.database_credentials_version)

  lifecycle {
    postcondition {
      condition     = length(self.secret_data) >= 16
      error_message = "The database password in Secret Manager must have at least 16 characters."
    }
  }
}

ephemeral "google_secret_manager_secret_version" "openrouter_api_key" {
  project = var.project_id
  secret  = "${var.name_prefix}-openrouter-source-key"
  version = tostring(var.openrouter_key_version)

  lifecycle {
    postcondition {
      condition     = length(trimspace(self.secret_data)) > 0
      error_message = "The OpenRouter key in Secret Manager must not be empty."
    }
  }
}

output "database_password" {
  value     = ephemeral.google_secret_manager_secret_version.database_password.secret_data
  sensitive = true
  ephemeral = true
}

output "openrouter_api_key" {
  value     = ephemeral.google_secret_manager_secret_version.openrouter_api_key.secret_data
  sensitive = true
  ephemeral = true
}
