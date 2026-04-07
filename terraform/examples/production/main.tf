# Production DabljaAR Deployment Example
# Full configuration with restricted admin access

module "dabljaar" {
  source = "../../"

  # Project
  project_id   = var.project_id
  project_name = "dabljaar"
  environment  = "prod"
  region       = var.region
  zone         = var.zone

  # Network - restrict admin access
  admin_cidr_blocks = var.admin_cidr_blocks

  # Compute - production sizing
  machine_type   = "n1-standard-8" # More CPU for production
  gpu_type       = "nvidia-tesla-t4"
  gpu_count      = 1
  enable_spot    = true # Still use spot for cost savings
  boot_disk_size = 100
  data_disk_size = 500 # More storage for production
}

# Variables
variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "zone" {
  type    = string
  default = "us-central1-a"
}

variable "admin_cidr_blocks" {
  type    = list(string)
  default = []
}

# Outputs
output "ssh_command" {
  value = module.dabljaar.ssh_command
}

output "ssh_tunnel_command" {
  value = module.dabljaar.ssh_tunnel_command
}

output "storage_bucket_name" {
  value = module.dabljaar.storage_bucket_name
}
