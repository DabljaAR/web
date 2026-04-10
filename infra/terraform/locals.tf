# =============================================================================
# Computed Values & Naming Conventions
# =============================================================================

locals {
  # Resource naming prefix: {project}-{environment}
  name_prefix = "${var.project_name}-${var.environment}"

  # Optional startup script content for first-boot host baseline setup.
  startup_script_content = var.startup_script_enabled ? templatefile("${path.module}/scripts/vm-bootstrap.sh.tftpl", {
    deployment_user            = var.deployment_user
    app_dir                    = "/home/${var.deployment_user}/web"
    env_secret_name            = var.vm_env_secret_name
    git_deploy_key_secret_name = var.vm_git_deploy_key_secret_name
  }) : null

  # Common labels applied to all resources
  common_labels = {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
  }
}
