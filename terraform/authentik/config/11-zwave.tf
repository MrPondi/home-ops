resource "authentik_provider_proxy" "zwavejs2mqtt" {
  name          = "Z-Wave JS Proxy Provider"
  external_host = "https://zwave.pondi.dev"

  authorization_flow  = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id

  mode = "forward_single"

  access_token_validity = "hours=6"
}

resource "authentik_application" "zwavejs2mqtt" {
  name              = "Z-Wave JS"
  slug              = "zwavejs2mqtt"
  protocol_provider = authentik_provider_proxy.zwavejs2mqtt.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/png/zwavejs2mqtt.png"
  meta_launch_url   = "https://zwave.pondi.dev"
  open_in_new_tab   = true
}