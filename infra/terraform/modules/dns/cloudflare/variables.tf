variable "zone_name" {
  description = "Cloudflare DNS zone apex (e.g. yourbrand.tech)"
  type        = string
}

variable "app_subdomain" {
  description = "App subdomain label within the zone (e.g. app -> app.yourbrand.tech)"
  type        = string
}

variable "target_ip" {
  description = "IPv4 address for A records (typically the VM static external IP)"
  type        = string
}

variable "include_rabbitmq" {
  description = "Create rabbitmq.<app_subdomain> A record for Caddy rabbitmq.{$DOMAIN} when DOMAIN is app.zone"
  type        = bool
  default     = true
}

variable "proxied" {
  description = "Cloudflare proxy (orange cloud). Keep false for Caddy ACME on the VM."
  type        = bool
  default     = false
}
