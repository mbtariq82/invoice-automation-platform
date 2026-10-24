terraform {
  required_version = ">= 1.11, < 2.0"

  backend "gcs" {
    bucket = "project-9ad4cdc4-734d-497d-81a-invoice-tfstate"
    prefix = "invoice-platform"
  }

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.8.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Separate the secret-read boundary so offline tests can override that module.
provider "google" {
  alias   = "secret_source"
  project = var.project_id
  region  = var.region
}
