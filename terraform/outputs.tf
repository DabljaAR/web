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

output "external_ip" {
  description = "External IP address of the instance"
  value       = module.compute.external_ip
}

# =============================================================================
# Application URLs
# =============================================================================

output "frontend_url" {
  description = "Frontend application URL"
  value       = "http://${module.compute.external_ip}:5173"
}

output "backend_url" {
  description = "Backend API URL"
  value       = "http://${module.compute.external_ip}:8000"
}

output "api_docs_url" {
  description = "API documentation (Swagger UI)"
  value       = "http://${module.compute.external_ip}:8000/docs"
}

output "flower_url" {
  description = "Celery Flower monitoring URL (admin access only)"
  value       = "http://${module.compute.external_ip}:5555"
}

output "minio_console_url" {
  description = "MinIO console URL (admin access only)"
  value       = "http://${module.compute.external_ip}:9001"
}

# =============================================================================
# Access Commands
# =============================================================================

output "ssh_command" {
  description = "SSH command to connect to the instance"
  value       = "gcloud compute ssh ${module.compute.instance_name} --zone=${var.zone} --project=${var.project_id}"
}

output "ssh_tunnel_command" {
  description = "SSH tunnel for admin services (Flower, MinIO console)"
  value       = "gcloud compute ssh ${module.compute.instance_name} --zone=${var.zone} --project=${var.project_id} -- -L 5555:localhost:5555 -L 9001:localhost:9001"
}

# =============================================================================
# Troubleshooting Commands
# =============================================================================

output "view_startup_logs" {
  description = "Command to view startup script logs"
  value       = "gcloud compute ssh ${module.compute.instance_name} --zone=${var.zone} --project=${var.project_id} --command='sudo tail -f /var/log/startup.log'"
}

output "view_docker_logs" {
  description = "Command to view Docker Compose logs"
  value       = "gcloud compute ssh ${module.compute.instance_name} --zone=${var.zone} --project=${var.project_id} --command='cd /opt/app && docker compose logs -f'"
}

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

output "model_bucket" {
  description = "GCS bucket for AI models"
  value       = module.storage.bucket_name
}

output "service_account_email" {
  description = "Service account email used by the VM"
  value       = module.iam.service_account_email
}
