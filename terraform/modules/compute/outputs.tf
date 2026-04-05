output "instance_name" {
  description = "Compute instance name"
  value       = google_compute_instance.vm.name
}

output "instance_id" {
  description = "Compute instance ID"
  value       = google_compute_instance.vm.instance_id
}

output "instance_self_link" {
  description = "Compute instance self link"
  value       = google_compute_instance.vm.self_link
}

output "external_ip" {
  description = "External IP address"
  value       = google_compute_address.vm.address
}

output "internal_ip" {
  description = "Internal IP address"
  value       = google_compute_instance.vm.network_interface[0].network_ip
}

output "data_disk_name" {
  description = "Data disk name"
  value       = google_compute_disk.data.name
}
