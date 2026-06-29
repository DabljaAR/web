# =============================================================================
# Cloudflare DNS Module - A records for app + optional rabbitmq host
# =============================================================================

data "cloudflare_zone" "this" {
  name = var.zone_name
}

locals {
  a_record_names = var.include_rabbitmq ? {
    (var.app_subdomain)             = var.target_ip
    "rabbitmq.${var.app_subdomain}" = var.target_ip
    } : {
    (var.app_subdomain) = var.target_ip
  }
}

resource "cloudflare_record" "a" {
  for_each = local.a_record_names

  zone_id         = data.cloudflare_zone.this.id
  name            = each.key
  type            = "A"
  value           = each.value
  proxied         = var.proxied
  allow_overwrite = true
  ttl             = var.proxied ? 1 : 300
}
