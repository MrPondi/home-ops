resource "authentik_provider_proxy" "victoria-logs" {
  name          = "Victoria Logs Proxy Provider"
  external_host = "https://victoria-logs.pondi.dev"

  authorization_flow  = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id

  mode = "forward_single"

  access_token_validity = "hours=6"
}

resource "authentik_outpost_provider_attachment" "victoria-logs" {
  outpost           = data.authentik_outpost.embedded.id
  protocol_provider = authentik_provider_proxy.victoria-logs.id
}

resource "authentik_application" "victoria-logs" {
  name              = "Victoria Logs"
  slug              = "victoria-logs"
  protocol_provider = authentik_provider_proxy.victoria-logs.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/victorialogs.svg"
  meta_launch_url   = "https://victoria-logs.pondi.dev"
  open_in_new_tab   = true
}

resource "authentik_policy_binding" "victoria-logs-access" {
  target = authentik_application.victoria-logs.uuid
  group  = authentik_group.metrics-access.id
  order  = 10
}