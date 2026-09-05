resource "authentik_provider_proxy" "hubble" {
  name          = "Hubble Proxy Provider"
  external_host = "https://hubble.pondi.dev"

  authorization_flow  = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id

  mode = "forward_single"

  access_token_validity = "hours=6"
}

resource "authentik_outpost_provider_attachment" "hubble" {
  outpost           = data.authentik_outpost.embedded.id
  protocol_provider = authentik_provider_proxy.hubble.id
}

resource "authentik_application" "hubble" {
  name              = "Hubble"
  slug              = "hubble"
  protocol_provider = authentik_provider_proxy.hubble.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/cilium.svg"
  meta_launch_url   = "https://hubble.pondi.dev"
  open_in_new_tab   = true
}

resource "authentik_policy_binding" "hubble-access" {
  target = authentik_application.hubble.uuid
  group  = authentik_group.metrics-access.id
  order  = 10
}
