resource "authentik_provider_proxy" "prowlarr" {
  name          = "Prowlarr Proxy Provider"
  external_host = "https://prowlarr.pondi.dev"

  authorization_flow  = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id

  mode = "forward_single"

  access_token_validity = "hours=6"
}

resource "authentik_application" "prowlarr" {
  name              = "Prowlarr"
  slug              = "prowlarr"
  protocol_provider = authentik_provider_proxy.prowlarr.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/png/prowlarr.png"
  meta_launch_url   = "https://prowlarr.pondi.dev"
  open_in_new_tab   = true
}

resource "authentik_policy_binding" "prowlarr-access" {
  target = authentik_application.prowlarr.uuid
  group  = authentik_group.torrent-mgmt.id
  order  = 10
}