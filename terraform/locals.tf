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
}
