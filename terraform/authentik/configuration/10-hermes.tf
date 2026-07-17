data "bitwarden-secrets_secret" "hermes" {
  id = "9ebc4c74-8001-46fb-8e3b-b48800da4b69"
}

resource "authentik_provider_oauth2" "hermes" {
  name          = "Hermes OAuth2 Provider"
  client_id     = jsondecode(data.bitwarden-secrets_secret.hermes.value)["HERMES_OIDC_CLIENT_ID"]
  client_secret = jsondecode(data.bitwarden-secrets_secret.hermes.value)["HERMES_OIDC_CLIENT_SECRET"]

  authorization_flow  = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id

  allowed_redirect_uris = [
    {
      matching_mode = "strict",
      redirect_uri_type = "authorization",
      url           = "https://hermes.pondi.dev/auth/callback",
    }
  ]

  property_mappings = [
    data.authentik_property_mapping_provider_scope.scope-email.id,
    data.authentik_property_mapping_provider_scope.scope-openid.id,
    data.authentik_property_mapping_provider_scope.scope-profile.id,
  ]

  signing_key = data.authentik_certificate_key_pair.self-signed.id
}

resource "authentik_application" "hermes" {
  name              = "Hermes agent"
  slug              = "hermes"
  protocol_provider = authentik_provider_oauth2.hermes.id
  meta_icon         = "https://cdn.jsdelivr.net/npm/@mdi/svg@latest/svg/robot-happy-outline.svg"
  meta_launch_url   = "https://hermes.pondi.dev"
  open_in_new_tab   = true
}

resource "authentik_policy_binding" "hermes-access" {
  target = authentik_application.hermes.uuid
  group  = authentik_group.ai-access.id
  order  = 10
}
