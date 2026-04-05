variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "roles" {
  description = "IAM roles to grant to the service account"
  type        = list(string)
  default = [
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/secretmanager.secretAccessor"
  ]
}

variable "gcs_bucket" {
  description = "GCS bucket name to grant access to"
  type        = string
}

variable "secret_ids" {
  description = "Secret Manager secret IDs to grant access to"
  type        = list(string)
  default     = []
}
