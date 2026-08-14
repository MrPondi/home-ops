data "bitwarden-secrets_secret" "qui" {
  id = "b739c73a-7533-49f3-be19-b3dc00cf5280"
}

resource "authentik_provider_oauth2" "qui" {
  name          = "Qui OAuth2 Provider"
  client_id     = jsondecode(data.bitwarden-secrets_secret.qui.value)["QUI_OIDC_CLIENT_ID"]
  client_secret = jsondecode(data.bitwarden-secrets_secret.qui.value)["QUI_OIDC_CLIENT_SECRET"]

  authorization_flow  = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id

  allowed_redirect_uris = [
    {
      matching_mode = "strict",
      redirect_uri_type = "authorization",
      url           = "https://qui.pondi.dev/api/auth/oidc/callback",
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
    data.authentik_property_mapping_provider_scope.scope-email.id,
    data.authentik_property_mapping_provider_scope.scope-openid.id,
    data.authentik_property_mapping_provider_scope.scope-profile.id,
  ]

  signing_key = data.authentik_certificate_key_pair.self-signed.id
}

resource "authentik_application" "qui" {
  name              = "Qui"
  slug              = "qui"
  protocol_provider = authentik_provider_oauth2.qui.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/qui.svg"
  meta_launch_url   = "https://qui.pondi.dev"
  open_in_new_tab   = true
}

resource "authentik_policy_binding" "qui-access" {
  target = authentik_application.qui.uuid
  group  = authentik_group.torrent-mgmt.id
  order  = 10
}