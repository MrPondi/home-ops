resource "authentik_provider_proxy" "bazarr" {
  name          = "Bazarr Proxy Provider"
  external_host = "https://bazarr.pondi.dev"

  authorization_flow  = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id

  mode = "forward_single"

  access_token_validity = "hours=6"
}

resource "authentik_application" "bazarr" {
  name              = "Bazarr"
  slug              = "bazarr"
  protocol_provider = authentik_provider_proxy.bazarr.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/bazarr.svg"
  meta_launch_url   = "https://bazarr.pondi.dev"
  open_in_new_tab   = true
}