resource "authentik_stage_prompt_field" "recovery-password" {
  name        = "homelab-recovery-field-password"
  field_key   = "password"
  label       = "Password"
  type        = "password"
  placeholder = "Password"
  order       = 500
}

resource "authentik_stage_prompt_field" "recovery-password-repeat" {
  name        = "homelab-recovery-field-password-repeat"
  field_key   = "password_repeat"
  label       = "Password (repeat)"
  type        = "password"
  placeholder = "Password (repeat)"
  order       = 501
}

resource "authentik_policy_password" "password-complexity" {
  name          = "homelab-password-complexity"
  error_message = "Password must be at least 8 characters long. It must contain at least 1 digit, 1 uppercase letter, and 1 lowercase letter."
  amount_digits = 1
  amount_lowercase = 1
  amount_uppercase = 1
  check_have_i_been_pwned = true
  check_static_rules = true
  check_zxcvbn = true
  length_min    = 8
}

resource "authentik_stage_prompt" "password-change" {
  name = "homelab-password-change-prompt"
  fields = [
    authentik_stage_prompt_field.recovery-password.id,
    authentik_stage_prompt_field.recovery-password-repeat.id,
  ]
  validation_policies = [
    authentik_policy_password.password-complexity.id,
  ]
}

resource "authentik_stage_identification" "main-identification" {
  name           = "homelab-authentication-identification"
  user_fields    = ["username", "email"]
  captcha_stage = authentik_stage_captcha.turnstile.id
  case_insensitive_matching = true
  enable_remember_me = true
  passwordless_flow = authentik_flow.passwordless-flow.uuid
  recovery_flow = authentik_flow.recovery.uuid
  webauthn_stage = authentik_stage_authenticator_validate.passwordless-webauthn.id
}

data "bitwarden-secrets_secret" "authentik" {
  id = "b142d67e-b08e-4f1e-b48d-b3ea00ddd070"
}

resource "authentik_stage_captcha" "turnstile" {
  name        = "cloudflare-turnstile"
  private_key = jsondecode(data.bitwarden-secrets_secret.authentik.value)["AUTHENTIK_TURNSTILE_SECRETKEY"]
  public_key  = jsondecode(data.bitwarden-secrets_secret.authentik.value)["AUTHENTIK_TURNSTILE_SITEKEY"]
  api_url = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
  js_url = "https://challenges.cloudflare.com/turnstile/v0/api.js"
  interactive = true
}