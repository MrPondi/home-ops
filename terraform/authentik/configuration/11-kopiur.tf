resource "authentik_provider_proxy" "kopiur" {
  name          = "Kopiur Proxy Provider"
  external_host = "https://kopiur.pondi.dev"

  authorization_flow  = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id

  mode = "forward_single"

  access_token_validity = "hours=6"

  basic_auth_enabled = true
  basic_auth_username_attribute = "KOPIUR_WEBUI_USERNAME"
  basic_auth_password_attribute = "KOPIUR_WEBUI_PASSWORD"
}

resource "authentik_outpost_provider_attachment" "kopiur" {
  outpost           = data.authentik_outpost.embedded.id
  protocol_provider = authentik_provider_proxy.kopiur.id
}

resource "authentik_application" "kopiur" {
  name              = "Kopiur"
  slug              = "kopiur"
  protocol_provider = authentik_provider_proxy.kopiur.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/kopia.svg"
  meta_launch_url   = "https://kopiur.pondi.dev"
  open_in_new_tab   = true
}

resource "authentik_policy_binding" "kopiur-access" {
  target = authentik_application.kopiur.uuid
  group  = authentik_group.admins.id
  order  = 10
}