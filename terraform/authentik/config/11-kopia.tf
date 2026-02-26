resource "authentik_provider_proxy" "kopia" {
  name          = "Kopia Proxy Provider"
  external_host = "https://kopia.pondi.dev"

  authorization_flow  = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id

  mode = "forward_single"

  access_token_validity = "hours=6"
}

resource "authentik_outpost_provider_attachment" "kopia" {
  outpost           = data.authentik_outpost.embedded.id
  protocol_provider = authentik_provider_proxy.kopia.id
}

resource "authentik_application" "kopia" {
  name              = "Kopia"
  slug              = "kopia"
  protocol_provider = authentik_provider_proxy.kopia.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/kopia.svg"
  meta_launch_url   = "https://kopia.pondi.dev"
  open_in_new_tab   = true
}

resource "authentik_policy_binding" "kopia-access" {
  target = authentik_application.kopia.uuid
  group  = authentik_group.admins.id
  order  = 10
}