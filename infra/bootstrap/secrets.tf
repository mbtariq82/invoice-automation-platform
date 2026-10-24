variable "name_prefix" {
  description = "Use the same resource prefix as the application stack."
  type        = string
  default     = "invoice-dev"
}

variable "credential_reader_members" {
  description = "Terraform operators allowed to read source credentials, for example user:you@example.com."
  type        = set(string)
  default     = []

  validation {
    condition     = !contains(var.credential_reader_members, "allUsers") && !contains(var.credential_reader_members, "allAuthenticatedUsers")
    error_message = "Grant source credential access only to specific Terraform operators."
  }
}

resource "google_project_service" "secret_manager" {
  project            = var.project_id
  service            = "secretmanager.googleapis.com"
  disable_on_destroy = false
}

resource "google_secret_manager_secret" "inputs" {
  for_each = {
    database_password  = "${var.name_prefix}-database-password"
    openrouter_api_key = "${var.name_prefix}-openrouter-source-key"
  }

  project   = var.project_id
  secret_id = each.value

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  depends_on = [google_project_service.secret_manager]
}

resource "google_secret_manager_secret_iam_member" "credential_reader" {
  for_each = {
    for pair in setproduct(keys(google_secret_manager_secret.inputs), var.credential_reader_members) :
    "${pair[0]}:${pair[1]}" => { secret = pair[0], member = pair[1] }
  }

  project   = var.project_id
  secret_id = google_secret_manager_secret.inputs[each.value.secret].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = each.value.member
}

output "credential_secret_ids" {
  description = "Add the initial values in the Secret Manager console; Terraform never accepts their plaintext as inputs."
  value       = { for key, secret in google_secret_manager_secret.inputs : key => secret.secret_id }
}
