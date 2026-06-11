resource "authentik_flow" "recovery" {
  name           = "Password Recovery"
  title          = "Password Recovery"
  slug           = "password-recovery-flow"
  designation    = "recovery"
}

resource "authentik_stage_identification" "password-recovery" {
  name           = "password-recovery-identification"
  user_fields    = ["username", "email"]
}

resource "authentik_stage_email" "password-recovery" {
  name = "password-recovery-email"
  template = "email/password_reset.html"
  subject = "Authentik Password Reset"
  activate_user_on_success = true
}

resource "authentik_flow_stage_binding" "recovery-identification" {
  target = authentik_flow.recovery.uuid
  stage  = authentik_stage_identification.password-recovery.id
  order  = 10
}

resource "authentik_flow_stage_binding" "recovery-email" {
  target = authentik_flow.recovery.uuid
  stage  = authentik_stage_email.password-recovery.id
  order  = 20
}

resource "authentik_flow_stage_binding" "recovery-password" {
  target = authentik_flow.recovery.uuid
  stage  = authentik_stage_prompt.password-change.id
  order  = 30
}

resource "authentik_flow_stage_binding" "recovery-write" {
  target = authentik_flow.recovery.uuid
  stage  = data.authentik_stage.default-password-change-write.id
  order  = 40
}