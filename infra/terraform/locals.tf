# =============================================================================
# Computed Values & Naming Conventions
# =============================================================================

locals {
  # Resource naming prefix: {project}-{environment}
  name_prefix = "${var.project_name}-${var.environment}"

  network_tag = "${var.project_name}-vm"

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

  # Secret file paths (defaults relative to infra/terraform). file() is only valid in .tf, not .tfvars.
  env_production_file_path    = var.env_production_file != "" ? var.env_production_file : "${path.root}/../../.env.production"
  github_deploy_key_file_path = var.github_deploy_key_file != "" ? var.github_deploy_key_file : "${path.root}/../../../keys/github_deploy_key"

  bootstrap_secret_values_from_files = merge(
    var.vm_env_secret_name != "" ? {
      (var.vm_env_secret_name) = file(local.env_production_file_path)
    } : {},
    var.vm_git_deploy_key_secret_name != "" ? {
      (var.vm_git_deploy_key_secret_name) = file(local.github_deploy_key_file_path)
    } : {},
  )

  bootstrap_secret_values = var.manage_secret_versions ? merge(
    local.bootstrap_secret_values_from_files,
    var.bootstrap_secret_values,
  ) : {}
}
