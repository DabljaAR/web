# =============================================================================
# DabljaAR Infrastructure - Root Module
# =============================================================================
# This provisions infrastructure (networking, firewall, compute, storage).
# =============================================================================

# Configure providers
provider "google" {
  project = var.project_id
  region  = var.region
}

# Enable required APIs
resource "google_project_service" "apis" {
  for_each = toset([
    "compute.googleapis.com",
    "storage.googleapis.com",
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

  name_prefix  = local.name_prefix
  project_id   = var.project_id
  network_id   = module.network.network_id
  subnet_cidr  = var.subnet_cidr
  public_ports = var.public_ports
  admin_ports  = var.admin_ports
  admin_cidrs  = var.admin_cidr_blocks
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
# IAM Module (Optional)
# =============================================================================
module "iam" {
  count  = var.enable_vm_service_account ? 1 : 0
  source = "./modules/iam"

  name_prefix = local.name_prefix
  project_id  = var.project_id
  roles       = var.vm_service_account_roles
  gcs_bucket  = module.storage.bucket_name
  secret_ids  = []

  depends_on = [google_project_service.apis]
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
  startup_script_content = local.startup_script_content
  service_account_email  = var.enable_vm_service_account ? module.iam[0].service_account_email : null
  service_account_scopes = var.vm_service_account_scopes
  labels                 = local.common_labels

  depends_on = [
    module.network,
    module.firewall,
    module.storage,
    module.iam
  ]
}
