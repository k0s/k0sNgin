# This module configures a GCS bucket for terraform state storage
# Once created, it is not itself imported to terraform state, so it is fire and forget
# The project is determined by the GOOGLE_PROJECT environment variable

provider "google" {
}

data "google_project" "current" {}

resource "google_storage_bucket" "terraform_state" {
  name          = "${data.google_project.current.project_id}-terraform-state"
  location      = var.location
  force_destroy = false

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 5
    }
    action {
      type = "Delete"
    }
  }

  uniform_bucket_level_access = true

  labels = {
    purpose = "terraform-state"
    managed = "terraform"
  }
}

output "bucket_name" {
  description = "The name of the GCS bucket for Terraform state"
  value       = google_storage_bucket.terraform_state.name
}
