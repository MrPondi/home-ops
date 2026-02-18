data "bitwarden-secrets_secret" "proxmox" {
  id = "b2579e58-9838-4556-b613-b3ee0000fa21"
}

resource "authentik_provider_oauth2" "proxmox" {
  name          = "Proxmox OAuth2 Provider"
  client_id     = jsondecode(data.bitwarden-secrets_secret.proxmox.value)["PROXMOX_OIDC_CLIENT_ID"]
  client_secret = jsondecode(data.bitwarden-secrets_secret.proxmox.value)["PROXMOX_OIDC_CLIENT_SECRET"]

  authorization_flow  = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id

  allowed_redirect_uris = [
    {
      matching_mode = "strict",
      url           = "https://pve.internal:8006",
    }
  ]

  property_mappings = [
    data.authentik_property_mapping_provider_scope.scope-email.id,
    data.authentik_property_mapping_provider_scope.scope-openid.id,
    data.authentik_property_mapping_provider_scope.scope-profile.id,
  ]

  signing_key = data.authentik_certificate_key_pair.self-signed.id
  sub_mode    = "user_email"
}

resource "authentik_application" "proxmox" {
  name              = "Proxmox"
  slug              = "proxmox"
  protocol_provider = authentik_provider_oauth2.proxmox.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/proxmox.svg"
  meta_launch_url   = "https://pve.internal:8006"
  open_in_new_tab   = true
}

resource "authentik_policy_binding" "proxmox-access" {
  target = authentik_application.proxmox.uuid
  group  = authentik_group.admins.id
  order  = 10
}