# =============================================================================
# DabljaAR Infrastructure - Root Module
# =============================================================================
# This deploys a GPU-enabled Spot VM running the DabljaAR video dubbing platform
# =============================================================================

# Configure providers
provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

# Enable required APIs
resource "google_project_service" "apis" {
  for_each = toset([
    "compute.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
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
  public_ports = local.public_ports
  admin_ports  = local.admin_ports
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
# Secrets Module
# =============================================================================
module "secrets" {
  source = "./modules/secrets"

  name_prefix   = local.name_prefix
  project_id    = var.project_id
  secret_names  = local.secret_names
  secret_values = local.secret_values
  labels        = local.common_labels

  depends_on = [google_project_service.apis]
}

# =============================================================================
# IAM Module
# =============================================================================
module "iam" {
  source = "./modules/iam"

  name_prefix = local.name_prefix
  project_id  = var.project_id
  gcs_bucket  = module.storage.bucket_name
  secret_ids  = module.secrets.secret_ids

  depends_on = [google_project_service.apis]
}

# =============================================================================
# Compute Module
# =============================================================================
module "compute" {
  source = "./modules/compute"

  name_prefix           = local.name_prefix
  project_id            = var.project_id
  region                = var.region
  zone                  = var.zone
  machine_type          = var.machine_type
  gpu_type              = var.gpu_type
  gpu_count             = var.gpu_count
  spot                  = var.enable_spot
  boot_disk_size        = var.boot_disk_size
  data_disk_size        = var.data_disk_size
  subnet_self_link      = module.network.subnet_self_link
  service_account_email = module.iam.service_account_email
  gcs_model_bucket      = module.storage.bucket_name
  app_repo_url          = var.app_repo_url
  app_repo_branch       = var.app_repo_branch
  labels                = local.common_labels

  depends_on = [
    module.network,
    module.firewall,
    module.iam,
    module.secrets,
    module.storage
  ]
}
