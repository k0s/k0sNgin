variable "github_app_installation_id" {
  description = "GitHub App installation ID for Cloud Build connection. Get this from the Cloud Build console after installing the GitHub App."
  type        = string
}

variable "github_oauth_token_secret_version" {
  description = "Secret Manager secret version for GitHub OAuth token (format: projects/PROJECT/secrets/SECRET/versions/VERSION). Required when using GitHub App."
  type        = string
}
