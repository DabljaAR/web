# =============================================================================
# DabljaAR Infrastructure - Root Module
# =============================================================================
# This provisions infrastructure (networking, firewall, compute, storage, DNS).
# =============================================================================

# Configure providers
provider "google" {
  project = var.project_id
  region  = var.region
}

# Cloudflare auth: set CLOUDFLARE_API_TOKEN in the shell (do not pass an empty api_token here —
# that overrides the env var and fails provider validation).
provider "cloudflare" {}

# Enable required APIs
resource "google_project_service" "apis" {
  for_each = toset([
    "compute.googleapis.com",
    "storage.googleapis.com",
    "secretmanager.googleapis.com",
  ])
  project = var.project_id
  service = each.value

  disable_on_destroy = false
}

# =============================================================================
# Network Module
# =============================================================================
module "network" {
  source = "./modules/network"

  name_prefix = local.name_prefix
  project_id  = var.project_id
  region      = var.region
  subnet_cidr = var.subnet_cidr

  depends_on = [google_project_service.apis]
}

# =============================================================================
# Firewall Module
# =============================================================================
module "firewall" {
  source = "./modules/firewall"

  name_prefix            = local.name_prefix
  project_id             = var.project_id
  network_id             = module.network.network_id
  subnet_cidr            = var.subnet_cidr
  public_ports           = var.public_ports
  admin_ports            = var.admin_ports
  admin_cidrs            = var.admin_cidr_blocks
  instance_tag           = local.network_tag
  enable_deploy_ssh      = var.enable_deploy_ssh
  deploy_ssh_cidr_blocks = var.deploy_ssh_cidr_blocks
}

# =============================================================================
# Storage Module
# =============================================================================
module "storage" {
  source = "./modules/storage"

  name_prefix = local.name_prefix
  project_id  = var.project_id
  location    = var.region
  labels      = local.common_labels

  depends_on = [google_project_service.apis]
}

# =============================================================================
# Secrets Module (bootstrap)
# =============================================================================
module "secrets" {
  count  = var.manage_secrets ? 1 : 0
  source = "./modules/secrets"

  name_prefix            = local.name_prefix
  project_id             = var.project_id
  use_fixed_secret_ids   = true
  secret_names           = compact([var.vm_env_secret_name, var.vm_git_deploy_key_secret_name])
  manage_secret_versions = var.manage_secret_versions
  secret_values          = local.bootstrap_secret_values
  labels                 = local.common_labels

  depends_on = [google_project_service.apis]
}

# =============================================================================
# IAM Module (Optional)
# =============================================================================
module "iam" {
  count  = var.enable_vm_service_account ? 1 : 0
  source = "./modules/iam"

  name_prefix = local.name_prefix
  project_id  = var.project_id
  roles       = var.vm_service_account_roles
  gcs_bucket  = module.storage.bucket_name
  secret_ids  = var.manage_secrets ? module.secrets[0].secret_ids : []

  depends_on = [
    google_project_service.apis,
    module.secrets,
  ]
}

# =============================================================================
# Compute Module
# =============================================================================
module "compute" {
  source = "./modules/compute"

  name_prefix            = local.name_prefix
  project_id             = var.project_id
  region                 = var.region
  zone                   = var.zone
  machine_type           = var.machine_type
  gpu_type               = var.gpu_type
  gpu_count              = var.gpu_count
  spot                   = var.enable_spot
  boot_disk_image        = var.boot_disk_image
  boot_disk_size         = var.boot_disk_size
  data_disk_size         = var.data_disk_size
  subnet_self_link       = module.network.subnet_self_link
  network_tag            = local.network_tag
  startup_script_content = local.startup_script_content
  service_account_email  = var.enable_vm_service_account ? module.iam[0].service_account_email : null
  service_account_scopes = var.vm_service_account_scopes
  enable_oslogin         = var.enable_oslogin
  ssh_public_keys        = var.vm_ssh_public_key != "" ? [var.vm_ssh_public_key] : []
  labels                 = local.common_labels

  depends_on = [
    module.network,
    module.firewall,
    module.storage,
    module.iam,
  ]
}

# =============================================================================
# DNS Module (Cloudflare) - optional
# =============================================================================
module "dns_cloudflare" {
  count  = var.dns_enabled ? 1 : 0
  source = "./modules/dns/cloudflare"

  zone_name      = var.dns_zone_name
  app_subdomain  = var.dns_app_subdomain
  target_ip      = module.compute.external_ip
  include_flower = true
  proxied        = var.dns_proxied

  depends_on = [module.compute]
}
