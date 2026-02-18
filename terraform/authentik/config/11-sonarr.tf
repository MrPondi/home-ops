resource "authentik_provider_proxy" "sonarr" {
  name          = "Sonarr Proxy Provider"
  external_host = "https://sonarr.pondi.dev"

  authorization_flow  = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id

  mode = "forward_single"

  access_token_validity = "hours=6"
}

resource "authentik_application" "sonarr" {
  name              = "Sonarr"
  slug              = "sonarr"
  protocol_provider = authentik_provider_proxy.sonarr.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/sonarr.svg"
  meta_launch_url   = "https://sonarr.pondi.dev"
  open_in_new_tab   = true
}

resource "authentik_policy_binding" "sonarr-access" {
  target = authentik_application.sonarr.uuid
  group  = authentik_group.torrent-mgmt.id
  order  = 10
}