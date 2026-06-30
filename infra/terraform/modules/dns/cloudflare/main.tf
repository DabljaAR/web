# =============================================================================
# Cloudflare DNS Module - A records for app + optional rabbitmq host
# =============================================================================

data "cloudflare_zone" "this" {
  name = var.zone_name
}

locals {
  a_record_names = merge(
    { (var.app_subdomain) = var.target_ip },
    var.include_rabbitmq ? { "rabbitmq.${var.app_subdomain}" = var.target_ip } : {},
    var.include_grafana ? { "grafana.${var.app_subdomain}" = var.target_ip } : {},
  )
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
