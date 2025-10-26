# You must first login:
# gcloud auth application-default login

#
# Error: Error creating Service: googleapi: Error 403:
# Cloud Run Admin API has not been used in project k0sngin before or it is disabled.
# Enable it by visiting
# https://console.developers.google.com/apis/api/run.googleapis.com/overview?project=k0sngin
# then retry. If you enabled this API recently, wait a few minutes for the action to propagate
# to our systems and retry.


provider "google" {
    project = "k0sngin"
}

resource "google_cloud_run_v2_service" "default" {
    name     = "k0sninja"
    location = "us-west1"
    client   = "terraform"

    template {
      containers {
        image = "gcr.io/k0sngin/k0sninja:latest"
        ports {
          container_port = 8000
        }
      }
    }
}

resource "google_cloud_run_v2_service_iam_member" "noauth" {
    location = google_cloud_run_v2_service.default.location
    name     = google_cloud_run_v2_service.default.name
    role     = "roles/run.invoker"
    member   = "allUsers"
}
