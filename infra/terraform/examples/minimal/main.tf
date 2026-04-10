# Minimal DabljaAR Deployment Example
# Deploys with all defaults - just provide required values

module "dabljaar" {
  source = "../../"

  project_id   = var.project_id
  project_name = "dabljaar"
  environment  = "dev"
  region       = var.region
  zone         = var.zone
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

output "external_ip" {
  value = module.dabljaar.external_ip
}

output "ssh_command" {
  value = module.dabljaar.ssh_command
}
