data "bitwarden-secrets_secret" "duo" {
  id = "c49f9345-bd8f-4646-9879-b3ee017d1b53"
}

resource "authentik_flow" "duo-push-2fa" {
  name           = "Duo Push 2FA"
  title          = "Duo Push 2FA"
  slug           = "duo-push-2fa"
  designation    = "stage_configuration"
  authentication = "require_authenticated"
}

resource "authentik_stage_authenticator_duo" "duo_setup" {
  name                  = "duo-push-2fa-setup"
  client_id             = jsondecode(data.bitwarden-secrets_secret.duo.value)["DUO_CLIENT_ID"]
  client_secret         = jsondecode(data.bitwarden-secrets_secret.duo.value)["DUO_CLIENT_SECRET"]
  api_hostname          = jsondecode(data.bitwarden-secrets_secret.duo.value)["DUO_API_HOSTNAME"]
  admin_integration_key = jsondecode(data.bitwarden-secrets_secret.duo.value)["DUO_ADMIN_INTEGRATION_KEY"]
  admin_secret_key      = jsondecode(data.bitwarden-secrets_secret.duo.value)["DUO_ADMIN_SECRET_KEY"]
  configure_flow        = authentik_flow.duo-push-2fa.uuid
}

resource "authentik_flow_stage_binding" "duo_setup" {
  target = authentik_flow.duo-push-2fa.uuid
  stage  = authentik_stage_authenticator_duo.duo_setup.id
  order  = 10
}

resource "authentik_flow" "duo-ldap-authentication-flow" {
  name        = "Duo LDAP Authentication Flow"
  title       = "Duo LDAP Authentication Flow"
  slug        = "duo-ldap-authentication-flow"
  designation = "authentication"
}

resource "authentik_flow_stage_binding" "duo-ldap-identification-stage" {
  target = authentik_flow.duo-ldap-authentication-flow.uuid
  stage  = authentik_stage_identification.ldap-identification-stage.id
  order  = 10
}

resource "authentik_stage_authenticator_validate" "ldap-duo-mfa-validation" {
  name                  = "ldap-duo-mfa-validation"
  device_classes        = ["duo"]
  not_configured_action = "skip"
}

resource "authentik_flow_stage_binding" "duo-ldap-mfa-validation" {
  target = authentik_flow.duo-ldap-authentication-flow.uuid
  stage  = authentik_stage_authenticator_validate.ldap-duo-mfa-validation.id
  order  = 20
}

resource "authentik_flow_stage_binding" "duo-ldap-authentication-login" {
  target = authentik_flow.duo-ldap-authentication-flow.uuid
  stage  = authentik_stage_user_login.ldap-authentication-login.id
  order  = 30
}

resource "authentik_provider_ldap" "duo" {
  name        = "Duo LDAP Provider"
  base_dn     = "dc=ldap-duo,dc=pondi,dc=dev"
  bind_flow   = authentik_flow.duo-ldap-authentication-flow.uuid
  unbind_flow = data.authentik_flow.default-invalidation-flow.id
}

resource "authentik_rbac_permission_role" "duo-provider-search" {
  role       = authentik_rbac_role.ldap-search.id
  model      = "authentik_providers_ldap.ldapprovider"
  permission = "authentik_providers_ldap.search_full_directory"
  object_id  = authentik_provider_ldap.duo.id
}