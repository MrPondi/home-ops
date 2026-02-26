resource "authentik_provider_proxy" "prometheus" {
  name          = "Prometheus Proxy Provider"
  external_host = "https://prometheus.pondi.dev"

  authorization_flow  = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id

  mode = "forward_single"

  access_token_validity = "hours=6"
}

resource "authentik_outpost_provider_attachment" "prometheus" {
  outpost           = data.authentik_outpost.embedded.id
  protocol_provider = authentik_provider_proxy.prometheus.id
}

resource "authentik_application" "prometheus" {
  name              = "Prometheus"
  slug              = "prometheus"
  protocol_provider = authentik_provider_proxy.prometheus.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/prometheus.svg"
  meta_launch_url   = "https://prometheus.pondi.dev"
  open_in_new_tab   = true
}

resource "authentik_group" "metrics-access" {
  name         = "Metrics Access"
}

resource "authentik_policy_binding" "prometheus-access" {
  target = authentik_application.prometheus.uuid
  group  = authentik_group.metrics-access.id
  order  = 10
}