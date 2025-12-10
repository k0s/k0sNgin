# This creates a trigger for using the in-built `cloudbuild.yaml` file as triggered on changes to `main` in Github
# The project is determined by the GOOGLE_PROJECT environment variable

terraform {
  backend "gcs" {
    bucket  = "k0sngin-terraform-state"
    prefix  = "k0sngin/trigger"
  }
}

provider "google" {
  project = "k0sngin"
}

# GitHub connection for Cloud Build
# Uses GitHub App for authentication (recommended approach)
# Note: This connection already exists. To import it, run:
#   terraform import google_cloudbuildv2_connection.github_connection projects/k0sngin/locations/us-west1/connections/k0sngin
resource "google_cloudbuildv2_connection" "github_connection" {
  location = "us-west1"
  name     = "k0sngin"

  github_config {
    app_installation_id = var.github_app_installation_id
    authorizer_credential {
      oauth_token_secret_version = var.github_oauth_token_secret_version
    }
  }
}

# Repository connection
# Links the GitHub repository to the existing connection
resource "google_cloudbuildv2_repository" "github_repo" {
  location           = "us-west1"
  name               = "k0sngin-repo"
  parent_connection  = google_cloudbuildv2_connection.github_connection.name
  remote_uri         = "https://github.com/k0s/k0sNgin.git"
}

# Cloud Build trigger for pushes to main branch
# Uses the repository connection created above
resource "google_cloudbuild_trigger" "main_branch_trigger" {
  location    = "us-west1"
  name        = "main-branch-trigger"

  # Use github block - works with v2 repository connections
  github {
    owner = "k0s"
    name  = "k0sNgin"
    push {
      branch = "^main$"
    }
  }

  filename = "cloudbuild.yaml"

  # Map _SHORT_SHA to Cloud Build's built-in SHORT_SHA variable
  # Cloud Build automatically provides SHORT_SHA for GitHub triggers
  # Use $$ to escape $ in Terraform strings
  #substitutions = {
  #  _SHORT_SHA = "$$SHORT_SHA"
  #}
}
