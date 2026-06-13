resource "authentik_flow" "enrollment" {
  name           = "Homelab Enrollment"
  title          = "Enrollment"
  slug           = "homelab-enrollment-flow"
  designation    = "enrollment"
}

resource "authentik_stage_invitation" "enrollment-invitation" {
  name = "homelab-enrollment-invitation"
}

resource "authentik_stage_prompt_field" "enrollment-username" {
  name        = "homelab-enrollment-field-username"
  field_key   = "username"
  label       = "Username"
  type        = "username"
  placeholder = "Username"
  order       = 400
}

resource "authentik_stage_prompt_field" "enrollment-name" {
  name        = "homelab-enrollment-field-name"
  field_key   = "name"
  label       = "Name"
  type        = "text"
  placeholder = "Name"
  order       = 401
}

resource "authentik_stage_prompt_field" "enrollment-email" {
  name        = "homelab-enrollment-field-email"
  field_key   = "email"
  label       = "Email"
  type        = "email"
  placeholder = "Email Address"
  order       = 402
}

resource "authentik_stage_prompt_field" "enrollment-password" {
  name        = "homelab-enrollment-field-password"
  field_key   = "password"
  label       = "Password"
  type        = "password"
  placeholder = "Password"
  order       = 403
}

resource "authentik_stage_prompt_field" "enrollment-password-repeat" {
  name        = "homelab-enrollment-field-password-repeat"
  field_key   = "password_repeat"
  label       = "Password (repeat)"
  type        = "password"
  placeholder = "Password (repeat)"
  order       = 404
}

resource "authentik_stage_prompt" "enrollment-prompt" {
  name = "homelab-enrollment-prompt"
  fields = [
    authentik_stage_prompt_field.enrollment-username.id,
    authentik_stage_prompt_field.enrollment-name.id,
    authentik_stage_prompt_field.enrollment-email.id,
    authentik_stage_prompt_field.enrollment-password.id,
    authentik_stage_prompt_field.enrollment-password-repeat.id,
  ]
  validation_policies = [
    authentik_policy_password.password-complexity.id,
  ]
}

resource "authentik_stage_user_write" "enrollment-write" {
  name                     = "homelab-user-write"
  create_users_as_inactive = true
  user_creation_mode       = "always_create"
  user_path_template       = "users"
  user_type                = "internal"
}

resource "authentik_stage_email" "email-verification" {
  name = "homelab-email-verification"
  template = "email/account_confirmation.html"
  subject = "Authentik Account Confirmation"
  activate_user_on_success = true
}

resource "authentik_flow_stage_binding" "enrollment-invitation" {
  target = authentik_flow.enrollment.uuid
  stage  = authentik_stage_invitation.enrollment-invitation.id
  order  = 10
}

resource "authentik_flow_stage_binding" "enrollment-prompt" {
  target = authentik_flow.enrollment.uuid
  stage  = authentik_stage_prompt.enrollment-prompt.id
  order  = 20
}

resource "authentik_flow_stage_binding" "enrollment-write" {
  target = authentik_flow.enrollment.uuid
  stage  = authentik_stage_user_write.enrollment-write.id
  order  = 30
}

resource "authentik_flow_stage_binding" "email-verification" {
  target = authentik_flow.enrollment.uuid
  stage  = authentik_stage_email.email-verification.id
  order  = 40
}