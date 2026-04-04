# =============================================================================
# Compute Module - Spot VM with GPU for AI Workloads
# =============================================================================

# External IP address
resource "google_compute_address" "vm" {
  name    = "${var.name_prefix}-ip"
  region  = var.region
  project = var.project_id
}

# Data disk (persists across preemptions)
resource "google_compute_disk" "data" {
  name    = "${var.name_prefix}-data"
  type    = var.data_disk_type
  size    = var.data_disk_size
  zone    = var.zone
  project = var.project_id
  labels  = var.labels

  lifecycle {
    prevent_destroy = false # Set to true for production
  }
}

# Compute instance
resource "google_compute_instance" "vm" {
  name         = "${var.name_prefix}-vm"
  machine_type = var.machine_type
  zone         = var.zone
  project      = var.project_id

  tags = [var.network_tag]

  boot_disk {
    initialize_params {
      image = var.boot_disk_image
      size  = var.boot_disk_size
      type  = var.boot_disk_type
    }
  }

  attached_disk {
    source      = google_compute_disk.data.self_link
    device_name = "data"
  }

  # GPU configuration
  guest_accelerator {
    type  = var.gpu_type
    count = var.gpu_count
  }

  # Required for GPU instances
  scheduling {
    on_host_maintenance = "TERMINATE"
    automatic_restart   = var.spot ? false : true
    preemptible         = var.spot
    provisioning_model  = var.spot ? "SPOT" : "STANDARD"
  }

  network_interface {
    subnetwork = var.subnet_self_link
    access_config {
      nat_ip = google_compute_address.vm.address
    }
  }

  service_account {
    email  = var.service_account_email
    scopes = ["cloud-platform"]
  }

  metadata = {
    startup-script = templatefile("${path.module}/templates/startup.sh.tpl", {
      name_prefix     = var.name_prefix
      data_disk_name  = "data"
      model_bucket    = var.gcs_model_bucket
      app_repo_url    = var.app_repo_url
      app_repo_branch = var.app_repo_branch
      project_id      = var.project_id
    })
    enable-oslogin = "TRUE"
  }

  labels = var.labels

  allow_stopping_for_update = true

  lifecycle {
    ignore_changes = [
      # Ignore changes to metadata startup-script during updates
      metadata["startup-script"]
    ]
  }
}
