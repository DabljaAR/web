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

variable "secret_values" {
  description = "Map of secret names to values"
  type        = map(string)
  sensitive   = true
}

variable "labels" {
  description = "Labels to apply to secrets"
  type        = map(string)
  default     = {}
}
