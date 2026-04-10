output "service_account_id" {
  description = "Service account ID"
  value       = google_service_account.vm.id
}

output "service_account_email" {
  description = "Service account email"
  value       = google_service_account.vm.email
}

output "service_account_name" {
  description = "Service account name"
  value       = google_service_account.vm.name
}
