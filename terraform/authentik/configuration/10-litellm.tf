data "bitwarden-secrets_secret" "litellm" {
  id = "63923a43-e89c-4a97-a4a0-b489011d8b3f"
}

resource "authentik_provider_oauth2" "litellm" {
  name          = "LiteLLM OAuth2 Provider"
  client_id     = jsondecode(data.bitwarden-secrets_secret.litellm.value)["LITELLM_OIDC_CLIENT_ID"]
  client_secret = jsondecode(data.bitwarden-secrets_secret.litellm.value)["LITELLM_OIDC_CLIENT_SECRET"]

  authorization_flow  = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id

  allowed_redirect_uris = [
    {
      matching_mode = "strict",
      redirect_uri_type = "authorization",
      url           = "https://litellm.pondi.dev/sso/callback",
    }
  ]

  property_mappings = [
    data.authentik_property_mapping_provider_scope.scope-email.id,
    data.authentik_property_mapping_provider_scope.scope-openid.id,
    data.authentik_property_mapping_provider_scope.scope-profile.id,
  ]

  signing_key = data.authentik_certificate_key_pair.self-signed.id
}

# resource "authentik_application" "litellm" {
#   name              = "LiteLLM"
#   slug              = "litellm"
#   protocol_provider = authentik_provider_oauth2.litellm.id
#   meta_icon         = "https://cdn.jsdelivr.net/gh/selfhst/icons/svg/litellm.svg"
#   meta_launch_url   = "https://litellm.pondi.dev"
#   open_in_new_tab   = true
# }

resource "authentik_group" "ai-access" {
  name         = "AI access"
}

# resource "authentik_policy_binding" "litellm-access" {
#   target = authentik_application.litellm.uuid
#   group  = authentik_group.ai-access.id
#   order  = 10
# }
