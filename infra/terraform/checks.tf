# =============================================================================
# Configuration checks
# =============================================================================

check "dns_zone_required" {
  assert {
    condition     = !var.dns_enabled || var.dns_zone_name != ""
    error_message = "dns_zone_name must be set when dns_enabled is true."
  }
}

check "bootstrap_secret_names" {
  assert {
    condition = !var.manage_secrets || (
      var.vm_env_secret_name != "" && var.vm_git_deploy_key_secret_name != ""
    )
    error_message = "vm_env_secret_name and vm_git_deploy_key_secret_name are required when manage_secrets is true."
  }
}

check "vm_ssh_for_deploy" {
  assert {
    condition     = !var.startup_script_enabled || var.vm_ssh_public_key != ""
    error_message = "vm_ssh_public_key is required when startup_script_enabled is true (GitHub Actions SSH deploy)."
  }
}
