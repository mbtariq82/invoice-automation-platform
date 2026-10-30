terraform {
  required_version = ">= 1.11, < 2.0"

  backend "gcs" {}

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.8.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 8.8.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

# Separate the secret-read boundary so offline tests can override that module.
provider "google" {
  alias   = "secret_source"
  project = var.project_id
  region  = var.region
}
