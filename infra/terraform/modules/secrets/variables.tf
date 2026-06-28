variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "secret_names" {
  description = "List of secret names to create"
  type        = list(string)
  default     = ["db-password", "secret-key", "minio-access-key", "minio-secret-key"]
}

variable "use_fixed_secret_ids" {
  description = "When true, secret_id equals each secret_names entry (no name_prefix). Use for bootstrap secrets like env-production."
  type        = bool
  default     = false
}

variable "manage_secret_versions" {
  description = "When true, create secret versions from secret_values. Set false to create empty secrets and add versions manually."
  type        = bool
  default     = true
}

variable "secret_values" {
  description = "Map of secret names to values (required keys must match secret_names when manage_secret_versions is true)"
  type        = map(string)
  sensitive   = true
  default     = {}
}

variable "labels" {
  description = "Labels to apply to secrets"
  type        = map(string)
  default     = {}
}
