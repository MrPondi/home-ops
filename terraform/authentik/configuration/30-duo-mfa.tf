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