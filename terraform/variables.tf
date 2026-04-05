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

# =============================================================================
# Application Configuration
# =============================================================================

variable "app_repo_url" {
  description = "Git repository URL for the application"
  type        = string
  default     = "https://github.com/your-org/dabljaar.git"
}

variable "app_repo_branch" {
  description = "Git branch to deploy"
  type        = string
  default     = "main"
}

# =============================================================================
# Secrets (Sensitive)
# =============================================================================

variable "db_password" {
  description = "PostgreSQL database password"
  type        = string
  sensitive   = true
}

variable "secret_key" {
  description = "Application secret key for JWT signing"
  type        = string
  sensitive   = true
}

variable "minio_access_key" {
  description = "MinIO access key"
  type        = string
  sensitive   = true
}

variable "minio_secret_key" {
  description = "MinIO secret key"
  type        = string
  sensitive   = true
}
