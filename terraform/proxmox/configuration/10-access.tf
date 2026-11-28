data "bitwarden-secrets_secret" "proxmox" {
  id = "b2579e58-9838-4556-b613-b3ee0000fa21"
}

resource "proxmox_realm_openid" "authentik" {
  realm      = "authentik"
  issuer_url = "https://auth.pondi.dev/application/o/proxmox/"
  client_id  = jsondecode(data.bitwarden-secrets_secret.proxmox.value)["PROXMOX_OIDC_CLIENT_ID"]

  client_key_wo         = jsondecode(data.bitwarden-secrets_secret.proxmox.value)["PROXMOX_OIDC_CLIENT_SECRET"]
  client_key_wo_version = 1

  autocreate     = true
  default        = true
  query_userinfo = true
  scopes         = "email profile proxmox"
  username_claim = "username"

  groups_autocreate = false
  groups_claim      = "proxmox_groups"
  groups_overwrite  = true
}

resource "proxmox_virtual_environment_group" "admins" {
  group_id = "admins-authentik"
  comment  = "authentik entitlement admins (Proxmox Admins) - Managed by Terraform"
}

resource "proxmox_acl" "admins" {
  group_id  = proxmox_virtual_environment_group.admins.group_id
  path      = "/"
  role_id   = "Administrator"
  propagate = true
}

resource "proxmox_virtual_environment_group" "authentik" {
  for_each = var.proxmox_access

  group_id = "${each.key}-authentik"
  comment  = "authentik entitlement ${each.key} (${each.value.group}) - Managed by Terraform"
}

resource "proxmox_acl" "authentik" {
  for_each = var.proxmox_access

  group_id  = proxmox_virtual_environment_group.authentik[each.key].group_id
  path      = each.value.path
  role_id   = each.value.role
  propagate = true
}
