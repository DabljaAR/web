# =============================================================================
# Firewall Module - Public and Admin Access Rules
# =============================================================================

# Allow public access to web services
resource "google_compute_firewall" "public" {
  name    = "${var.name_prefix}-allow-public"
  network = var.network_id
  project = var.project_id

  allow {
    protocol = "tcp"
    ports    = var.public_ports
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = [var.instance_tag]
}

# Allow admin access from specific IPs
resource "google_compute_firewall" "admin" {
  count   = length(var.admin_cidrs) > 0 ? 1 : 0
  name    = "${var.name_prefix}-allow-admin"
  network = var.network_id
  project = var.project_id

  allow {
    protocol = "tcp"
    ports    = var.admin_ports
  }

  source_ranges = var.admin_cidrs
  target_tags   = [var.instance_tag]
}

# Allow internal communication within VPC
resource "google_compute_firewall" "internal" {
  name    = "${var.name_prefix}-allow-internal"
  network = var.network_id
  project = var.project_id

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "udp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "icmp"
  }

  source_ranges = [var.subnet_cidr]
}

# Allow SSH via IAP (Identity-Aware Proxy) - recommended for secure access
resource "google_compute_firewall" "iap_ssh" {
  name    = "${var.name_prefix}-allow-iap-ssh"
  network = var.network_id
  project = var.project_id

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  # IAP's IP range
  source_ranges = ["35.235.240.0/20"]
  target_tags   = [var.instance_tag]
}

# Allow SSH from GitHub Actions / CI (public IP, key-only auth)
resource "google_compute_firewall" "deploy_ssh" {
  count   = var.enable_deploy_ssh && length(var.deploy_ssh_cidr_blocks) > 0 ? 1 : 0
  name    = "${var.name_prefix}-allow-deploy-ssh"
  network = var.network_id
  project = var.project_id

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = var.deploy_ssh_cidr_blocks
  target_tags   = [var.instance_tag]
}
