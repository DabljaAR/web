output "public_firewall_id" {
  description = "Public firewall rule ID"
  value       = google_compute_firewall.public.id
}

output "admin_firewall_id" {
  description = "Admin firewall rule ID"
  value       = length(google_compute_firewall.admin) > 0 ? google_compute_firewall.admin[0].id : null
}

output "internal_firewall_id" {
  description = "Internal firewall rule ID"
  value       = google_compute_firewall.internal.id
}

output "iap_ssh_firewall_id" {
  description = "IAP SSH firewall rule ID"
  value       = google_compute_firewall.iap_ssh.id
}
