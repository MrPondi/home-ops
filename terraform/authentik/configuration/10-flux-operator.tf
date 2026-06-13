data "bitwarden-secrets_secret" "flux-operator" {
  id = "283d4479-b085-4a96-bf42-b3fd00123cb3"
}

resource "authentik_property_mapping_provider_scope" "flux-operator-admin" {
  name       = "Flux Operator Admin"
  scope_name = "admin"
  expression = "return { 'admin': 'True' } if request.user.is_superuser or ak_is_group_member(request.user, name='Flux Operator Admins') else {}"
}

resource "authentik_provider_oauth2" "flux-operator" {
  name          = "Flux Operator OAuth2 Provider"
  client_id     = jsondecode(data.bitwarden-secrets_secret.flux-operator.value)["FLUX_OPERATOR_OIDC_CLIENT_ID"]
  client_secret = jsondecode(data.bitwarden-secrets_secret.flux-operator.value)["FLUX_OPERATOR_OIDC_CLIENT_SECRET"]

  authorization_flow  = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id

  allowed_redirect_uris = [
    {
      matching_mode = "strict",
      redirect_uri_type = "authorization",
      url           = "https://flux-operator.pondi.dev/oauth2/callback",
    }
  ]

  property_mappings = [
    authentik_property_mapping_provider_scope.flux-operator-admin.id,
    data.authentik_property_mapping_provider_scope.scope-email.id,
    data.authentik_property_mapping_provider_scope.scope-openid.id,
    data.authentik_property_mapping_provider_scope.scope-profile.id,
  ]

  signing_key = data.authentik_certificate_key_pair.self-signed.id
}

resource "authentik_application" "flux-operator" {
  name              = "Flux Operator"
  slug              = "flux-operator"
  protocol_provider = authentik_provider_oauth2.flux-operator.id
  meta_icon         = "https://raw.githubusercontent.com/controlplaneio-fluxcd/flux-operator/refs/heads/main/docs/logo/flux-operator-icon.svg"
  meta_launch_url   = "https://flux-operator.pondi.dev"
  open_in_new_tab   = true
}

resource "authentik_group" "flux-operator-users" {
  name         = "Flux Operator Users"
}

resource "authentik_group" "flux-operator-admins" {
  name         = "Flux Operator Admins"
  parents      = [authentik_group.flux-operator-users.id]
}

resource "authentik_policy_binding" "flux-operator-access" {
  target = authentik_application.flux-operator.uuid
  group  = authentik_group.flux-operator-users.id
  order  = 10
}