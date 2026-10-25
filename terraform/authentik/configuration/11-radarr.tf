data "bitwarden-secrets_secret" "radarr" {
  # TODO: replace with the Bitwarden secret id of the `radarr` item (needs RADARR_OIDC_CLIENT_ID / _CLIENT_SECRET / _OIDC_USER)
  id = "00000000-0000-0000-0000-000000000000"
}

resource "authentik_provider_oauth2" "radarr" {
  name          = "Radarr OAuth2 Provider"
  client_id     = jsondecode(data.bitwarden-secrets_secret.radarr.value)["RADARR_OIDC_CLIENT_ID"]
  client_secret = jsondecode(data.bitwarden-secrets_secret.radarr.value)["RADARR_OIDC_CLIENT_SECRET"]

  authorization_flow = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow  = data.authentik_flow.default-invalidation-flow.id

  allowed_redirect_uris = [
    {
      matching_mode     = "strict",
      redirect_uri_type = "authorization",
      url               = "https://radarr.pondi.dev/signin-oidc",
    }
  ]

  property_mappings = [
    data.authentik_property_mapping_provider_scope.scope-email.id,
    data.authentik_property_mapping_provider_scope.scope-openid.id,
    data.authentik_property_mapping_provider_scope.scope-profile.id,
  ]

  signing_key = data.authentik_certificate_key_pair.self-signed.id
}

resource "authentik_application" "radarr" {
  name              = "Radarr"
  slug              = "radarr"
  protocol_provider = authentik_provider_oauth2.radarr.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/radarr.svg"
  meta_launch_url   = "https://radarr.pondi.dev"
  open_in_new_tab   = true
}

resource "authentik_policy_binding" "radarr-access" {
  target = authentik_application.radarr.uuid
  group  = authentik_group.torrent-mgmt.id
  order  = 10
}
