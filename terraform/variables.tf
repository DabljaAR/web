# =============================================================================
# Project Configuration
# =============================================================================

variable "project_id" {
  description = "GCP project ID"
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "Project ID must be 6-30 characters, lowercase letters, digits, or hyphens."
  }
}

variable "project_name" {
  description = "Short name for resource naming (e.g., 'dabljaar')"
  type        = string
  default     = "dabljaar"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,15}$", var.project_name))
    error_message = "Project name must be 3-16 characters, lowercase letters, digits, or hyphens."
  }
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

# =============================================================================
# Region & Zone Configuration
# =============================================================================

variable "region" {
  description = "GCP region for resources"
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "GCP zone for compute resources (must have T4 GPUs available)"
  type        = string
  default     = "us-central1-a"
}

# =============================================================================
# Network Configuration
# =============================================================================

variable "subnet_cidr" {
  description = "CIDR block for the subnet"
  type        = string
  default     = "10.0.0.0/24"

  validation {
    condition     = can(cidrhost(var.subnet_cidr, 0))
    error_message = "Subnet CIDR must be a valid CIDR block."
  }
}

variable "admin_cidr_blocks" {
  description = "CIDR blocks allowed to access admin ports (SSH, Flower, MinIO console)"
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for cidr in var.admin_cidr_blocks : can(cidrhost(cidr, 0))])
    error_message = "All admin CIDR blocks must be valid CIDR notation."
  }
}

variable "public_ports" {
  description = "Ports exposed publicly (typically Caddy 80/443 only in production)"
  type        = list(number)
  default     = [80, 443]
}

variable "admin_ports" {
  description = "Ports exposed to admin_cidr_blocks only"
  type        = list(number)
  default     = [5555, 9001]
}

# =============================================================================
# Compute Configuration
# =============================================================================

variable "machine_type" {
  description = "GCP machine type for the VM"
  type        = string
  default     = "n1-standard-4"
}

variable "gpu_type" {
  description = "GPU type to attach (nvidia-tesla-t4 recommended for cost)"
  type        = string
  default     = "nvidia-tesla-t4"

  validation {
    condition     = contains(["nvidia-tesla-t4", "nvidia-tesla-v100", "nvidia-tesla-p100", "nvidia-tesla-a100"], var.gpu_type)
    error_message = "GPU type must be one of: nvidia-tesla-t4, nvidia-tesla-v100, nvidia-tesla-p100, nvidia-tesla-a100."
  }
}

variable "gpu_count" {
  description = "Number of GPUs to attach"
  type        = number
  default     = 1

  validation {
    condition     = var.gpu_count >= 0 && var.gpu_count <= 4
    error_message = "GPU count must be between 0 and 4."
  }
}

variable "enable_spot" {
  description = "Use Spot VM for ~70% cost savings (can be preempted)"
  type        = bool
  default     = true
}

variable "startup_script_enabled" {
  description = "Enable VM startup bootstrap script for host baseline configuration"
  type        = bool
  default     = false
}

variable "deployment_user" {
  description = "Primary Linux user for deployment directory ownership"
  type        = string
  default     = "ubuntu"
}

variable "enable_vm_service_account" {
  description = "Enable creation and attachment of a dedicated VM service account"
  type        = bool
  default     = false
}

variable "vm_service_account_roles" {
  description = "Project IAM roles granted to the VM service account"
  type        = list(string)
  default = [
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/secretmanager.secretAccessor"
  ]
}

variable "vm_service_account_scopes" {
  description = "OAuth scopes applied when attaching VM service account"
  type        = list(string)
  default     = ["https://www.googleapis.com/auth/cloud-platform"]
}

variable "vm_env_secret_name" {
  description = "Optional Secret Manager secret name that contains full .env.production content"
  type        = string
  default     = ""

  validation {
    condition     = var.vm_env_secret_name == "" || can(regex("^[A-Za-z0-9_-]+$", var.vm_env_secret_name))
    error_message = "vm_env_secret_name must be empty or a valid Secret Manager secret name."
  }
}

variable "vm_git_deploy_key_secret_name" {
  description = "Optional Secret Manager secret name that contains private SSH deploy key for GitHub clone"
  type        = string
  default     = ""

  validation {
    condition     = var.vm_git_deploy_key_secret_name == "" || can(regex("^[A-Za-z0-9_-]+$", var.vm_git_deploy_key_secret_name))
    error_message = "vm_git_deploy_key_secret_name must be empty or a valid Secret Manager secret name."
  }
}

variable "boot_disk_image" {
  description = "Boot disk image family path for the VM"
  type        = string
  default     = "projects/deeplearning-platform-release/global/images/family/common-cu128-ubuntu-2204-nvidia-570"

  validation {
    condition     = can(regex("^projects/[a-z0-9-]+/global/images/family/[a-z0-9-]+$", var.boot_disk_image))
    error_message = "boot_disk_image must be in the form: projects/<project>/global/images/family/<family>."
  }
}

variable "boot_disk_size" {
  description = "Boot disk size in GB"
  type        = number
  default     = 50

  validation {
    condition     = var.boot_disk_size >= 30 && var.boot_disk_size <= 500
    error_message = "Boot disk size must be between 30 and 500 GB."
  }
}

variable "data_disk_size" {
  description = "Data disk size in GB (persists across preemptions)"
  type        = number
  default     = 100

  validation {
    condition     = var.data_disk_size >= 50 && var.data_disk_size <= 2000
    error_message = "Data disk size must be between 50 and 2000 GB."
  }
}

