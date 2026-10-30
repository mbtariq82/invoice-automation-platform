variable "project_id" {
  description = "Existing GCP project with billing enabled."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "Use a GCP project ID of 6 to 30 lowercase letters, numbers and hyphens."
  }
}

variable "region" {
  description = "Region shared by Cloud Run, Cloud SQL, Storage and Artifact Registry."
  type        = string
  default     = "europe-west2"
}

variable "name_prefix" {
  description = "Prefix for resources in this development environment."
  type        = string
  default     = "invoice-dev"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,18}[a-z0-9]$", var.name_prefix))
    error_message = "Use 4 to 20 lowercase letters, numbers and hyphens, starting with a letter."
  }
}

variable "database_credentials_version" {
  description = "Numbered version of the bootstrap database-password secret; updates SQL and the database URL together."
  type        = number
  default     = 1

  validation {
    condition     = var.database_credentials_version >= 1 && floor(var.database_credentials_version) == var.database_credentials_version
    error_message = "The credential version must be a positive integer."
  }
}

variable "openrouter_key_version" {
  description = "Numbered version of the bootstrap OpenRouter source-key secret."
  type        = number
  default     = 1

  validation {
    condition     = var.openrouter_key_version >= 1 && floor(var.openrouter_key_version) == var.openrouter_key_version
    error_message = "The key version must be a positive integer."
  }
}

variable "vertex_ai_model" {
  description = "Vertex AI Gemini model identifier; required when deploying the application."
  type        = string
  default     = ""
}

variable "deploy_application" {
  description = "Enable after pushing the API image; creates the service and migration job."
  type        = bool
  default     = false
}

variable "container_image" {
  description = "Immutable Artifact Registry image URL ending in @sha256:<digest>."
  type        = string
  default     = ""

  validation {
    condition     = var.container_image == "" || can(regex("@sha256:[a-f0-9]{64}$", var.container_image))
    error_message = "Use an image digest instead of a mutable image tag."
  }
}

variable "frontend_google_client_id" {
  description = "Google OAuth web client ID used by the React sign-in flow; this is a public identifier, not a secret."
  type        = string
  default     = ""

  validation {
    condition     = var.frontend_google_client_id == "" || can(regex("^[0-9]+-[a-z0-9-]+\\.apps\\.googleusercontent\\.com$", var.frontend_google_client_id))
    error_message = "Use a Google OAuth web client ID ending in .apps.googleusercontent.com."
  }
}

variable "invoker_members" {
  description = "IAM principals allowed to call the private API, such as user:you@example.com."
  type        = set(string)
  default     = []

  validation {
    condition     = !contains(var.invoker_members, "allUsers") && !contains(var.invoker_members, "allAuthenticatedUsers")
    error_message = "Grant specific principals access; the development API must remain private."
  }
}

variable "admin_members" {
  description = "Authenticated subjects or emails allowed to access all invoices."
  type        = set(string)
  default     = []

  validation {
    condition     = !contains(var.admin_members, "allUsers") && !contains(var.admin_members, "allAuthenticatedUsers")
    error_message = "Grant administrative access only to specific identities."
  }
}

variable "deletion_protection" {
  description = "Protect the database, API and migration job from accidental deletion."
  type        = bool
  default     = true
}

variable "api_token_audiences" {
  description = "Audiences accepted for signed Google ID tokens: the service URL or an explicit OAuth client ID."
  type        = set(string)
  default     = []

  validation {
    condition     = alltrue([for audience in var.api_token_audiences : trimspace(audience) != "" && !strcontains(audience, ",")])
    error_message = "Token audiences must be nonempty values without commas."
  }
}
