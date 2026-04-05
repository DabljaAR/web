variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
}

variable "zone" {
  description = "GCP zone"
  type        = string
}

variable "machine_type" {
  description = "Machine type"
  type        = string
  default     = "n1-standard-4"
}

variable "gpu_type" {
  description = "GPU type"
  type        = string
  default     = "nvidia-tesla-t4"
}

variable "gpu_count" {
  description = "Number of GPUs"
  type        = number
  default     = 1
}

variable "spot" {
  description = "Use Spot VM (preemptible)"
  type        = bool
  default     = true
}

variable "boot_disk_image" {
  description = "Boot disk image"
  type        = string
  default     = "projects/deeplearning-platform-release/global/images/family/common-cu128-ubuntu-2204-nvidia-570"
}

variable "boot_disk_size" {
  description = "Boot disk size in GB"
  type        = number
  default     = 50
}

variable "boot_disk_type" {
  description = "Boot disk type"
  type        = string
  default     = "pd-balanced"
}

variable "data_disk_size" {
  description = "Data disk size in GB"
  type        = number
  default     = 100
}

variable "data_disk_type" {
  description = "Data disk type"
  type        = string
  default     = "pd-balanced"
}

variable "subnet_self_link" {
  description = "Subnet self link"
  type        = string
}

variable "service_account_email" {
  description = "Service account email"
  type        = string
}

variable "network_tag" {
  description = "Network tag for firewall rules"
  type        = string
  default     = "dabljaar-vm"
}

variable "gcs_model_bucket" {
  description = "GCS bucket containing AI models"
  type        = string
}

variable "app_repo_url" {
  description = "Git repository URL"
  type        = string
}

variable "app_repo_branch" {
  description = "Git branch to deploy"
  type        = string
  default     = "main"
}

variable "labels" {
  description = "Labels to apply to resources"
  type        = map(string)
  default     = {}
}
