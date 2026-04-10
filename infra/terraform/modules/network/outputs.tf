output "network_id" {
  description = "VPC network ID"
  value       = google_compute_network.main.id
}

output "network_name" {
  description = "VPC network name"
  value       = google_compute_network.main.name
}

output "network_self_link" {
  description = "VPC network self link"
  value       = google_compute_network.main.self_link
}

output "subnet_id" {
  description = "Subnet ID"
  value       = google_compute_subnetwork.main.id
}

output "subnet_name" {
  description = "Subnet name"
  value       = google_compute_subnetwork.main.name
}

output "subnet_self_link" {
  description = "Subnet self link"
  value       = google_compute_subnetwork.main.self_link
}
