output "service_url" {
  description = "The URL of the Cloud Run service"
  value       = google_cloud_run_v2_service.default.uri
}

output "service_name" {
  description = "The name of the Cloud Run service"
  value       = google_cloud_run_v2_service.default.name
}

output "service_location" {
  description = "The location/region of the Cloud Run service"
  value       = google_cloud_run_v2_service.default.location
}
