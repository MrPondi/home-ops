data "bitwarden-secrets_secret" "minio" {
  id = "bf6713b4-8ae0-4100-9208-b3dc00d6a8ae"
}

resource "authentik_property_mapping_provider_scope" "minio-policy" {
  name       = "MinIO Policy"
  scope_name = "policy"
  expression = <<EOF
return {
  "policy": "consoleAdmin"
    if request.user.is_superuser
    or request.user.group_attributes().get("minio_admin", False)
    else "readonly"
}
EOF
}

resource "authentik_provider_oauth2" "minio" {
  name          = "MinIO OAuth2 Provider"
  client_id     = jsondecode(data.bitwarden-secrets_secret.minio.value)["MINIO_OIDC_CLIENT_ID"]
  client_secret = jsondecode(data.bitwarden-secrets_secret.minio.value)["MINIO_OIDC_CLIENT_SECRET"]

  authorization_flow  = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id

  allowed_redirect_uris = [
    {
      matching_mode = "strict",
      url           = "https://minio.pondi.dev/oauth_callback",
    }
  ]

  property_mappings = [
    authentik_property_mapping_provider_scope.minio-policy.id,
    data.authentik_property_mapping_provider_scope.scope-email.id,
    data.authentik_property_mapping_provider_scope.scope-openid.id,
    data.authentik_property_mapping_provider_scope.scope-profile.id,
  ]

  signing_key = data.authentik_certificate_key_pair.self-signed.id
}

resource "authentik_application" "minio" {
  name              = "MinIO"
  slug              = "minio"
  protocol_provider = authentik_provider_oauth2.minio.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/minio.svg"
  meta_launch_url   = "https://minio.pondi.dev"
  open_in_new_tab   = true
}