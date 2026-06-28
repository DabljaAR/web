output "secret_ids" {
  description = "List of created Secret Manager secret IDs (for IAM bindings)"
  value       = [for s in google_secret_manager_secret.secrets : s.secret_id]
}

output "secret_names" {
  description = "Map of logical secret keys to Secret Manager secret IDs"
  value       = { for k, s in google_secret_manager_secret.secrets : k => s.secret_id }
}
