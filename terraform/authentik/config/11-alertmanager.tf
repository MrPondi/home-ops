resource "authentik_provider_proxy" "alertmanager" {
  name          = "Alertmanager Proxy Provider"
  external_host = "https://alertmanager.pondi.dev"

  authorization_flow  = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id

  mode = "forward_single"

  access_token_validity = "hours=6"
}

resource "authentik_outpost_provider_attachment" "alertmanager" {
  outpost           = data.authentik_outpost.embedded.id
  protocol_provider = authentik_provider_proxy.alertmanager.id
}

resource "authentik_application" "alertmanager" {
  name              = "Alertmanager"
  slug              = "alertmanager"
  protocol_provider = authentik_provider_proxy.alertmanager.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/prometheus.svg"
  meta_launch_url   = "https://alertmanager.pondi.dev"
  open_in_new_tab   = true
}

resource "authentik_policy_binding" "alertmanager-access" {
  target = authentik_application.alertmanager.uuid
  group  = authentik_group.metrics-access.id
  order  = 10
}