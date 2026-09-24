data "bitwarden-secrets_secret" "netronome" {
  id = "28eb64c9-a5fd-4f35-8141-b4cf01716766"
}

resource "authentik_provider_oauth2" "netronome" {
  name          = "Netronome OAuth2 Provider"
  client_id     = jsondecode(data.bitwarden-secrets_secret.netronome.value)["NETRONOME_OIDC_CLIENT_ID"]
  client_secret = jsondecode(data.bitwarden-secrets_secret.netronome.value)["NETRONOME_OIDC_CLIENT_SECRET"]

  authorization_flow = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow  = data.authentik_flow.default-invalidation-flow.id

  allowed_redirect_uris = [
    {
      matching_mode     = "strict"
      redirect_uri_type = "authorization"
      url               = "https://speedtest.pondi.dev/api/auth/oidc/callback"
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

resource "authentik_application" "netronome" {
  name              = "Netronome"
  slug              = "netronome"
  protocol_provider = authentik_provider_oauth2.netronome.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/netronome.svg"
  meta_launch_url   = "https://speedtest.pondi.dev"
  open_in_new_tab   = true
}

resource "authentik_policy_binding" "netronome-access" {
  target = authentik_application.netronome.uuid
  group  = authentik_group.metrics-access.id
  order  = 10
}
