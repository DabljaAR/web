output "secret_ids" {
  description = "List of created secret IDs"
  value       = [for s in google_secret_manager_secret.secrets : s.secret_id]
}

output "secret_names" {
  description = "Map of secret keys to full secret names"
  value       = { for k, s in google_secret_manager_secret.secrets : k => s.secret_id }
}
