# =============================================================================
# Computed Values & Naming Conventions
# =============================================================================

locals {
  # Resource naming prefix: {project}-{environment}
  name_prefix = "${var.project_name}-${var.environment}"

  # Common labels applied to all resources
  common_labels = {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
  }

  # Public ports accessible from anywhere
  public_ports = [80, 443, 5173, 8000]

  # Admin ports restricted to specific IPs
  admin_ports = [22, 5555, 9000, 9001]

  # Secret names (non-sensitive for iteration)
  secret_names = ["db-password", "secret-key", "minio-access-key", "minio-secret-key"]

  # Secret values (sensitive)
  secret_values = {
    "db-password"      = var.db_password
    "secret-key"       = var.secret_key
    "minio-access-key" = var.minio_access_key
    "minio-secret-key" = var.minio_secret_key
  }
}
