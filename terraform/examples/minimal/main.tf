# Minimal DabljaAR Deployment Example
# Deploys with all defaults - just provide required values

module "dabljaar" {
  source = "../../"

  project_id   = var.project_id
  project_name = "dabljaar"
  environment  = "dev"
  region       = var.region
  zone         = var.zone

  # Secrets
  db_password      = var.db_password
  secret_key       = var.secret_key
  minio_access_key = var.minio_access_key
  minio_secret_key = var.minio_secret_key

  # App config
  app_repo_url = var.app_repo_url
}

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

output "frontend_url" {
  value = module.dabljaar.frontend_url
}

output "ssh_command" {
  value = module.dabljaar.ssh_command
}
