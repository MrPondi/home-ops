
resource "authentik_flow" "passwordless-flow" {
  name           = "Homelab Passwordless Flow"
  title          = "Homelab Passwordless Flow"
  slug           = "homelab-passwordless-flow"
  designation    = "authentication"
}

resource "authentik_stage_authenticator_validate" "passwordless-webauthn" {
  name                  = "passwordless-webauthn-validation"
  device_classes        = ["webauthn"]
  not_configured_action = "configure"
  webauthn_user_verification = "required"
  configuration_stages = [
    data.authentik_stage.default-authenticator-webauthn-setup.id,
    ]
}

resource "authentik_flow_stage_binding" "passwordless-webauthn" {
  target = authentik_flow.passwordless-flow.uuid
  stage  = authentik_stage_authenticator_validate.passwordless-webauthn.id
  order  = 10
}

resource "authentik_flow_stage_binding" "authentication-login" {
  target = authentik_flow.passwordless-flow.uuid
  stage  = data.authentik_stage.default-authentication-login.id
  order  = 20
}