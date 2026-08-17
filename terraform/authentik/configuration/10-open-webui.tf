resource "authentik_property_mapping_provider_scope" "open-webui-scope" {
  name       = "Open WebUI Profile"
  scope_name = "open-webui"
  expression = <<EOF
entitlement_names = {
  entitlement.name
  for entitlement in request.user.app_entitlements(provider.application)
}

return {
  "roles": "admin" if (request.user.is_superuser or "Admins" in entitlement_names) else "user",
  "picture": request.user.avatar
}
EOF
}

data "bitwarden-secrets_secret" "open-webui" {
  id = "b78c5dd6-627c-4202-ac34-b4a900c305ee"
}

resource "authentik_provider_oauth2" "open-webui" {
  name          = "Open WebUI OAuth2 Provider"
  client_id     = jsondecode(data.bitwarden-secrets_secret.open-webui.value)["OPEN_WEBUI_OIDC_CLIENT_ID"]
  client_secret = jsondecode(data.bitwarden-secrets_secret.open-webui.value)["OPEN_WEBUI_OIDC_CLIENT_SECRET"]

  authorization_flow  = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id

  allowed_redirect_uris = [
    {
      matching_mode = "strict",
      redirect_uri_type = "authorization",
      url           = "https://chat.pondi.dev/auth/callback",
    }
  ]

  grant_types = [
    "authorization_code",
    "hybrid",
    "implicit",
    "client_credentials",
    "password",
    "urn:ietf:params:oauth:grant-type:device_code",
    "refresh_token"
  ]

  property_mappings = [
    authentik_property_mapping_provider_scope.open-webui-scope.id,
    data.authentik_property_mapping_provider_scope.scope-email.id,
    data.authentik_property_mapping_provider_scope.scope-openid.id,
    data.authentik_property_mapping_provider_scope.scope-profile.id,
  ]

  logout_uri = "https://chat.pondi.dev/oauth/backchannel-logout"

  signing_key = data.authentik_certificate_key_pair.self-signed.id
}

resource "authentik_application" "open-webui" {
  name              = "Open WebUI"
  slug              = "open-webui"
  protocol_provider = authentik_provider_oauth2.open-webui.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/open-webui-light.svg"
  meta_launch_url   = "https://chat.pondi.dev"
  open_in_new_tab   = true
}

resource "authentik_application_entitlement" "open-webui-admins" {
  name        = "Admins"
  application = authentik_application.open-webui.uuid
}

resource "authentik_policy_binding" "open-webui-admins-access" {
  target = authentik_application_entitlement.open-webui-admins.id
  group  = authentik_group.ai-admins.id
  order  = 10
}

resource "authentik_policy_binding" "open-webui-access" {
  target = authentik_application.open-webui.uuid
  group  = authentik_group.ai-access.id
  order  = 10
}
