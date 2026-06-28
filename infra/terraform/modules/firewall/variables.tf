variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "network_id" {
  description = "VPC network ID"
  type        = string
}

variable "subnet_cidr" {
  description = "Subnet CIDR for internal firewall rules"
  type        = string
}

variable "instance_tag" {
  description = "Network tag for target instances"
  type        = string
  default     = "dabljaar-vm"
}

variable "public_ports" {
  description = "Ports to allow from anywhere (web services)"
  type        = list(number)
  default     = [80, 443]
}

variable "admin_ports" {
  description = "Ports to allow from admin CIDRs only (optional admin UIs)"
  type        = list(number)
  default     = [5555, 9001]
}

variable "admin_cidrs" {
  description = "CIDR blocks allowed admin access"
  type        = list(string)
  default     = []
}

variable "enable_deploy_ssh" {
  description = "Allow SSH (port 22) from deploy_ssh_cidr_blocks for GitHub Actions deploy"
  type        = bool
  default     = true
}

variable "deploy_ssh_cidr_blocks" {
  description = "CIDR blocks allowed SSH for CI deploy (GitHub Actions). Key-only auth; tighten CIDRs when possible."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}
