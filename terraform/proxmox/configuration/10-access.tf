data "bitwarden-secrets_secret" "proxmox" {
  id = "b2579e58-9838-4556-b613-b3ee0000fa21"
}

# authentik OIDC login. The "proxmox" scope (terraform/authentik 10-proxmox.tf) emits the
# user's Proxmox app entitlements as proxmox_groups; PVE maps each to "<name>-authentik".
# groups_autocreate is off, so only the groups declared below are ever joined.
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

# One PVE group + ACL per entry in the shared proxmox-access.auto.tfvars.
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
