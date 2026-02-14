resource "authentik_provider_proxy" "radarr" {
  name          = "Radarr Proxy Provider"
  external_host = "https://radarr.pondi.dev"

  authorization_flow  = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id

  mode = "forward_single"

  access_token_validity = "hours=6"
}

resource "authentik_application" "radarr" {
  name              = "Radarr"
  slug              = "radarr"
  protocol_provider = authentik_provider_proxy.radarr.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/radarr.svg"
  meta_launch_url   = "https://radarr.pondi.dev"
  open_in_new_tab   = true
}