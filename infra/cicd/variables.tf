variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "europe-west2"
}

variable "name_prefix" {
  type    = string
  default = "invoice-dev"
}

variable "github_repository" {
  description = "Exact owner/repository, used with numeric IDs to restrict the workflow."
  type        = string
}

variable "github_repository_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]+$", var.github_repository_id))
    error_message = "Use the immutable numeric GitHub repository ID."
  }
}

variable "github_owner_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]+$", var.github_owner_id))
    error_message = "Use the immutable numeric GitHub owner ID."
  }
}
