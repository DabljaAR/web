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
  default     = [80, 443, 5173, 8000]
}

variable "admin_ports" {
  description = "Ports to allow from admin CIDRs only"
  type        = list(number)
  default     = [22, 5555, 9000, 9001]
}

variable "admin_cidrs" {
  description = "CIDR blocks allowed admin access"
  type        = list(string)
  default     = []
}
