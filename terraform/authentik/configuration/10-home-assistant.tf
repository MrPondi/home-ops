data "bitwarden-secrets_secret" "home-assistant" {
  id = "de31c87e-d0c4-4322-a08a-b3dc00c7575d"
}

resource "authentik_provider_oauth2" "home-assistant" {
  name          = "Home Assistant OAuth2 Provider"
  client_id     = jsondecode(data.bitwarden-secrets_secret.home-assistant.value)["HASS_OIDC_CLIENT_ID"]
  client_secret = jsondecode(data.bitwarden-secrets_secret.home-assistant.value)["HASS_OIDC_CLIENT_SECRET"]

  authorization_flow  = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id

  allowed_redirect_uris = [
    {
      matching_mode = "strict",
      redirect_uri_type = "authorization",
      url           = "https://hass.pondi.dev/auth/openid/callback",
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

resource "authentik_application" "home-assistant" {
  name              = "Home Assistant"
  slug              = "home-assistant"
  protocol_provider = authentik_provider_oauth2.home-assistant.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/home-assistant-alt.svg"
  meta_launch_url   = "https://hass.pondi.dev"
  open_in_new_tab   = true
}

resource "authentik_group" "hass-users" {
  name         = "Home Assistant Users"
}

resource "authentik_group" "hass-admins" {
  name         = "Home Assistant Admins"
  parents      = [authentik_group.hass-users.id]
}

resource "authentik_policy_binding" "hass-access" {
  target = authentik_application.home-assistant.uuid
  group  = authentik_group.hass-users.id
  order  = 10
}