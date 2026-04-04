# =============================================================================
# Secrets Module - Secret Manager for Credentials
# =============================================================================

# Create secrets (using non-sensitive list for iteration)
resource "google_secret_manager_secret" "secrets" {
  for_each  = toset(var.secret_names)
  secret_id = "${var.name_prefix}-${each.key}"
  project   = var.project_id

  replication {
    auto {}
  }

  labels = var.labels
}

# Add secret versions (the actual values)
resource "google_secret_manager_secret_version" "secrets" {
  for_each    = toset(var.secret_names)
  secret      = google_secret_manager_secret.secrets[each.key].id
  secret_data = var.secret_values[each.key]
}
