data "bitwarden-secrets_secret" "toolhive" {
  id = "23a04dd3-8b3a-4972-aed8-b4a600aca640"
}

resource "authentik_provider_oauth2" "toolhive" {
  name          = "ToolHive OAuth2 Provider"
  client_id     = jsondecode(data.bitwarden-secrets_secret.toolhive.value)["TOOLHIVE_OIDC_CLIENT_ID"]
  client_secret = jsondecode(data.bitwarden-secrets_secret.toolhive.value)["TOOLHIVE_OIDC_CLIENT_SECRET"]

  authorization_flow  = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id

  allowed_redirect_uris = [
    {
      matching_mode = "strict",
      redirect_uri_type = "authorization",
      url           = "https://mcp.pondi.dev/oauth/callback",
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
    data.authentik_property_mapping_provider_scope.scope-offline_access.id,
  ]

  signing_key = data.authentik_certificate_key_pair.self-signed.id
}

resource "authentik_application" "toolhive" {
  name              = "ToolHive"
  slug              = "toolhive"
  protocol_provider = authentik_provider_oauth2.toolhive.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/toolhive.svg"
  meta_launch_url   = "https://mcp.pondi.dev"
  open_in_new_tab   = true
}

resource "authentik_policy_binding" "toolhive-access" {
  target = authentik_application.toolhive.uuid
  group  = authentik_group.ai-access.id
  order  = 10
}
