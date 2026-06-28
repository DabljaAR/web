# =============================================================================
# Secrets Module - Secret Manager for Credentials
# =============================================================================

locals {
  secret_ids = {
    for name in var.secret_names : name => var.use_fixed_secret_ids ? name : "${var.name_prefix}-${name}"
  }
}

# Create secrets (using non-sensitive list for iteration)
resource "google_secret_manager_secret" "secrets" {
  for_each  = local.secret_ids
  secret_id = each.value
  project   = var.project_id

  replication {
    auto {}
  }

  labels = var.labels
}

# Add secret versions (the actual values)
resource "google_secret_manager_secret_version" "secrets" {
  for_each = var.manage_secret_versions ? local.secret_ids : {}

  secret      = google_secret_manager_secret.secrets[each.key].id
  secret_data = var.secret_values[each.key]
}
