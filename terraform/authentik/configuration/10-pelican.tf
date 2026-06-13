data "bitwarden-secrets_secret" "pelican" {
  id = "8034330e-4ac4-4791-b750-b3dc00c06a20"
}

resource "authentik_provider_oauth2" "pelican" {
  name          = "Pelican OAuth2 Provider"
  client_id     = jsondecode(data.bitwarden-secrets_secret.pelican.value)["PELICAN_OIDC_CLIENT_ID"]
  client_secret = jsondecode(data.bitwarden-secrets_secret.pelican.value)["PELICAN_OIDC_CLIENT_SECRET"]

  authorization_flow  = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id

  allowed_redirect_uris = [
    {
      matching_mode = "strict",
      redirect_uri_type = "authorization",
      url           = "https://gamepanel.pondi.dev/auth/oauth/callback/authentik",
    }
  ]

  property_mappings = [
    data.authentik_property_mapping_provider_scope.scope-email.id,
    data.authentik_property_mapping_provider_scope.scope-openid.id,
    data.authentik_property_mapping_provider_scope.scope-profile.id,
  ]

  signing_key = data.authentik_certificate_key_pair.self-signed.id
}

resource "authentik_application" "pelican" {
  name              = "Pelican"
  slug              = "pelican"
  protocol_provider = authentik_provider_oauth2.pelican.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/pelican-panel.svg"
  meta_launch_url   = "https://gamepanel.pondi.dev"
  open_in_new_tab   = true
}

resource "authentik_group" "pelican-access" {
  name         = "Gamepanel access"
}

resource "authentik_policy_binding" "pelican-access" {
  target = authentik_application.pelican.uuid
  group  = authentik_group.pelican-access.id
  order  = 10
}