resource "authentik_provider_proxy" "qbittorrent" {
  name          = "Qbittorrent Proxy Provider"
  external_host = "https://qbittorrent.pondi.dev"

  authorization_flow  = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id

  mode = "forward_single"

  access_token_validity = "hours=6"
}

resource "authentik_application" "qbittorrent" {
  name              = "Qbittorrent"
  slug              = "qbittorrent"
  protocol_provider = authentik_provider_proxy.qbittorrent.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/qbittorrent.svg"
  meta_launch_url   = "https://qbittorrent.pondi.dev"
  open_in_new_tab   = true
}