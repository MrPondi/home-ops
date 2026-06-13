resource "authentik_provider_proxy" "teslamate" {
  name          = "Teslamate Proxy Provider"
  external_host = "https://teslamate.pondi.dev"

  authorization_flow  = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id

  mode = "forward_single"

  access_token_validity = "hours=6"
}

resource "authentik_outpost_provider_attachment" "teslamate" {
  outpost           = data.authentik_outpost.embedded.id
  protocol_provider = authentik_provider_proxy.teslamate.id
}

resource "authentik_application" "teslamate" {
  name              = "Teslamate"
  slug              = "teslamate"
  protocol_provider = authentik_provider_proxy.teslamate.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/teslamate.svg"
  meta_launch_url   = "https://teslamate.pondi.dev"
  open_in_new_tab   = true
}

resource "authentik_policy_binding" "teslamate-access" {
  target = authentik_application.teslamate.uuid
  group  = authentik_group.admins.id
  order  = 10
}