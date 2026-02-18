data "bitwarden-secrets_secret" "autobrr" {
  id = "126203bb-d362-4b04-b0a7-b3dc00ce6ed0"
}

resource "authentik_provider_oauth2" "autobrr" {
  name          = "Autobrr OAuth2 Provider"
  client_id     = jsondecode(data.bitwarden-secrets_secret.autobrr.value)["AUTOBRR_OIDC_CLIENT_ID"]
  client_secret = jsondecode(data.bitwarden-secrets_secret.autobrr.value)["AUTOBRR_OIDC_CLIENT_SECRET"]

  authorization_flow  = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id

  allowed_redirect_uris = [
    {
      matching_mode = "strict",
      url           = "https://autobrr.pondi.dev/api/auth/oidc/callback",
    }
  ]

  property_mappings = [
    data.authentik_property_mapping_provider_scope.scope-email.id,
    data.authentik_property_mapping_provider_scope.scope-openid.id,
    data.authentik_property_mapping_provider_scope.scope-profile.id,
  ]

  signing_key = data.authentik_certificate_key_pair.self-signed.id
}

resource "authentik_application" "autobrr" {
  name              = "Autobrr"
  slug              = "autobrr"
  protocol_provider = authentik_provider_oauth2.autobrr.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/autobrr.svg"
  meta_launch_url   = "https://autobrr.pondi.dev"
  open_in_new_tab   = true
}

resource "authentik_policy_binding" "autobrr-access" {
  target = authentik_application.autobrr.uuid
  group  = authentik_group.torrent-mgmt.id
  order  = 10
}