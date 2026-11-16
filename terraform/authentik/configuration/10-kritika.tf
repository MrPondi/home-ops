data "bitwarden-secrets_secret" "kritika" {
  id = "0e81938c-f654-4e66-a2c4-b503016cd0d1"
}

resource "authentik_provider_oauth2" "kritika" {
  name          = "Kritika OAuth2 Provider"
  client_id     = jsondecode(data.bitwarden-secrets_secret.kritika.value)["KRITIKA_OIDC_CLIENT_ID"]
  client_secret = jsondecode(data.bitwarden-secrets_secret.kritika.value)["KRITIKA_OIDC_CLIENT_SECRET"]

  authorization_flow = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow  = data.authentik_flow.default-invalidation-flow.id

  allowed_redirect_uris = [
    {
      matching_mode     = "strict",
      redirect_uri_type = "authorization",
      url               = "https://kritika.pondi.dev/auth/callback/oidc",
    }
  ]

  grant_types = [
    "authorization_code",
    "refresh_token"
  ]

  property_mappings = [
    data.authentik_property_mapping_provider_scope.scope-email.id,
    data.authentik_property_mapping_provider_scope.scope-openid.id,
    data.authentik_property_mapping_provider_scope.scope-profile.id,
  ]

  signing_key = data.authentik_certificate_key_pair.self-signed.id
}

resource "authentik_application" "kritika" {
  name              = "Kritika"
  slug              = "kritika"
  protocol_provider = authentik_provider_oauth2.kritika.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/github-copilot.svg"
  meta_launch_url   = "https://kritika.pondi.dev"
  open_in_new_tab   = true
}

resource "authentik_policy_binding" "kritika-access" {
  target = authentik_application.kritika.uuid
  group  = authentik_group.admins.id
  order  = 10
}
