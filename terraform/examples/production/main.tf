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

  # Secrets
  db_password      = var.db_password
  secret_key       = var.secret_key
  minio_access_key = var.minio_access_key
  minio_secret_key = var.minio_secret_key

  # App
  app_repo_url    = var.app_repo_url
  app_repo_branch = "main"
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

variable "db_password" {
  type      = string
  sensitive = true
}

variable "secret_key" {
  type      = string
  sensitive = true
}

variable "minio_access_key" {
  type      = string
  sensitive = true
}

variable "minio_secret_key" {
  type      = string
  sensitive = true
}

variable "app_repo_url" {
  type = string
}

# Outputs
output "frontend_url" {
  value = module.dabljaar.frontend_url
}

output "backend_url" {
  value = module.dabljaar.backend_url
}

output "api_docs_url" {
  value = module.dabljaar.api_docs_url
}

output "ssh_command" {
  value = module.dabljaar.ssh_command
}

output "ssh_tunnel_command" {
  value = module.dabljaar.ssh_tunnel_command
}

output "model_bucket" {
  value = module.dabljaar.model_bucket
}
