resource "authentik_provider_proxy" "collabora" {
  name          = "Collabora Proxy Provider"
  external_host = "https://office.pondi.dev"

  authorization_flow = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow  = data.authentik_flow.default-invalidation-flow.id

  mode = "forward_single"

  access_token_validity = "hours=6"

  basic_auth_enabled            = true
  basic_auth_username_attribute = "COLLABORA_ADMIN_USERNAME"
  basic_auth_password_attribute = "COLLABORA_ADMIN_PASSWORD"
}

resource "authentik_outpost_provider_attachment" "collabora" {
  outpost           = data.authentik_outpost.embedded.id
  protocol_provider = authentik_provider_proxy.collabora.id
}

resource "authentik_application" "collabora" {
  name              = "Nextcloud Collabora"
  slug              = "collabora"
  protocol_provider = authentik_provider_proxy.collabora.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/png/collabora-office.png"
  meta_launch_url   = "https://office.pondi.dev/browser/dist/admin/admin.html"
  open_in_new_tab   = true
}

resource "authentik_policy_binding" "collabora-access" {
  target = authentik_application.collabora.uuid
  group  = authentik_group.nextcloud-admins.id
  order  = 10
}