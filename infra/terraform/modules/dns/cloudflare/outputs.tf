output "zone_id" {
  description = "Cloudflare zone ID"
  value       = data.cloudflare_zone.this.id
}

output "app_fqdn" {
  description = "Application FQDN (DOMAIN value for .env.production)"
  value       = "${var.app_subdomain}.${var.zone_name}"
}

output "rabbitmq_fqdn" {
  description = "RabbitMQ management UI FQDN when include_rabbitmq is true"
  value       = var.include_rabbitmq ? "rabbitmq.${var.app_subdomain}.${var.zone_name}" : null
}

output "deploy_hostname" {
  description = "Hostname for GitHub Actions GCP_VM_HOST (stable DNS name)"
  value       = "${var.app_subdomain}.${var.zone_name}"
}

output "record_ids" {
  description = "Map of record name to Cloudflare record ID"
  value       = { for k, r in cloudflare_record.a : k => r.id }
}
