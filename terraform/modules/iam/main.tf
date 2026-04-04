# =============================================================================
# IAM Module - Service Account and Role Bindings
# =============================================================================

# Service Account for the VM
resource "google_service_account" "vm" {
  account_id   = "${var.name_prefix}-vm-sa"
  display_name = "DabljaAR VM Service Account"
  project      = var.project_id
}

# Grant minimal required roles to the service account
resource "google_project_iam_member" "vm_roles" {
  for_each = toset(var.roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.vm.email}"
}

# Grant access to GCS bucket
resource "google_storage_bucket_iam_member" "vm_bucket_access" {
  count  = var.gcs_bucket != null ? 1 : 0
  bucket = var.gcs_bucket
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.vm.email}"
}

# Grant access to secrets
resource "google_secret_manager_secret_iam_member" "vm_secret_access" {
  for_each  = toset(var.secret_ids)
  project   = var.project_id
  secret_id = each.value
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.vm.email}"
}
