# =============================================================================
# Instance Information
# =============================================================================

output "instance_name" {
  description = "Name of the compute instance"
  value       = module.compute.instance_name
}

output "instance_zone" {
  description = "Zone where the instance is deployed"
  value       = var.zone
}

output "project_id" {
  description = "GCP project ID"
  value       = var.project_id
}

output "external_ip" {
  description = "External IP address of the instance"
  value       = module.compute.external_ip
}

output "deploy_hostname" {
  description = "Hostname for GitHub Actions GCP_VM_HOST (FQDN when DNS enabled, else external IP)"
  value       = var.dns_enabled ? module.dns_cloudflare[0].deploy_hostname : module.compute.external_ip
}

output "app_fqdn" {
  description = "Application FQDN when DNS is enabled (set DOMAIN in .env.production to this value)"
  value       = var.dns_enabled ? module.dns_cloudflare[0].app_fqdn : null
}

output "rabbitmq_fqdn" {
  description = "RabbitMQ management UI FQDN when DNS is enabled"
  value       = var.dns_enabled ? module.dns_cloudflare[0].rabbitmq_fqdn : null
}

# =============================================================================
# Access Commands
# =============================================================================

output "ssh_command" {
  description = "SSH command to connect to the instance"
  value       = "gcloud compute ssh ${module.compute.instance_name} --zone=${var.zone} --project=${var.project_id}"
}

output "ssh_tunnel_command" {
  description = "SSH tunnel for admin-only services"
  value       = "gcloud compute ssh ${module.compute.instance_name} --zone=${var.zone} --project=${var.project_id} -- -L 5555:localhost:5555 -L 9001:localhost:9001"
}

# =============================================================================
# Troubleshooting
# =============================================================================

output "check_gpu_status" {
  description = "Command to check GPU status"
  value       = "gcloud compute ssh ${module.compute.instance_name} --zone=${var.zone} --project=${var.project_id} --command='nvidia-smi'"
}

# =============================================================================
# Resource IDs (for reference)
# =============================================================================

output "network_id" {
  description = "VPC network ID"
  value       = module.network.network_id
}

output "subnet_id" {
  description = "Subnet ID"
  value       = module.network.subnet_id
}

output "storage_bucket_name" {
  description = "Provisioned GCS bucket name"
  value       = module.storage.bucket_name
}

output "vm_service_account_email" {
  description = "Service account attached to VM (null when disabled)"
  value       = var.enable_vm_service_account ? module.iam[0].service_account_email : null
}

output "firewall_rule_ids" {
  description = "Created firewall rule IDs"
  value = {
    public     = module.firewall.public_firewall_id
    admin      = module.firewall.admin_firewall_id
    internal   = module.firewall.internal_firewall_id
    iap_ssh    = module.firewall.iap_ssh_firewall_id
    deploy_ssh = module.firewall.deploy_ssh_firewall_id
  }
}
