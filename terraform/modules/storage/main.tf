# =============================================================================
# Storage Module - GCS Bucket
# =============================================================================

# Random suffix for globally unique bucket name
resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# GCS bucket
resource "google_storage_bucket" "models" {
  name          = "${var.name_prefix}-models-${random_id.bucket_suffix.hex}"
  location      = var.location
  project       = var.project_id
  force_destroy = var.force_destroy

  uniform_bucket_level_access = true

  versioning {
    enabled = var.enable_versioning
  }

  dynamic "lifecycle_rule" {
    for_each = var.enable_versioning ? [1] : []
    content {
      action {
        type = "Delete"
      }
      condition {
        num_newer_versions = var.max_versions
        with_state         = "ARCHIVED"
      }
    }
  }

  labels = var.labels
}
