data "bitwarden-secrets_secret" "proxmox" {
  id = "b2579e58-9838-4556-b613-b3ee0000fa21"
}

# Entitlement names become PVE groups "<name>-authentik" (realm groups-claim, managed in
# terraform/proxmox). Both sides are driven by the shared proxmox-access.auto.tfvars.
resource "authentik_property_mapping_provider_scope" "proxmox" {
  name       = "Proxmox Groups"
  scope_name = "proxmox"
  expression = <<EOF
entitlement_names = {
  entitlement.name
  for entitlement in request.user.app_entitlements(provider.application)
}

return { "proxmox_groups": sorted(entitlement_names) }
EOF
}

resource "authentik_provider_oauth2" "proxmox" {
  name          = "Proxmox OAuth2 Provider"
  client_id     = jsondecode(data.bitwarden-secrets_secret.proxmox.value)["PROXMOX_OIDC_CLIENT_ID"]
  client_secret = jsondecode(data.bitwarden-secrets_secret.proxmox.value)["PROXMOX_OIDC_CLIENT_SECRET"]

  authorization_flow = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow  = data.authentik_flow.default-invalidation-flow.id

  allowed_redirect_uris = [
    {
      matching_mode     = "strict",
      redirect_uri_type = "authorization",
      url               = "https://pve.pondi.dev",
    }
  ]

  grant_types = [
    "authorization_code",
    "hybrid",
    "implicit",
    "client_credentials",
    "password",
    "urn:ietf:params:oauth:grant-type:device_code",
    "refresh_token"
  ]

  property_mappings = [
    authentik_property_mapping_provider_scope.proxmox.id,
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
  meta_launch_url   = "https://pve.pondi.dev"
  open_in_new_tab   = true
}

# Login only: membership alone grants nothing inside PVE.
resource "authentik_group" "proxmox-users" {
  name = "Proxmox Users"
}

resource "authentik_group" "proxmox" {
  for_each = var.proxmox_access

  name    = each.value.group
  parents = [authentik_group.proxmox-users.id]
}

resource "authentik_application_entitlement" "proxmox" {
  for_each = var.proxmox_access

  name        = each.key
  application = authentik_application.proxmox.uuid
}

resource "authentik_policy_binding" "proxmox-entitlement" {
  for_each = var.proxmox_access

  target = authentik_application_entitlement.proxmox[each.key].id
  group  = authentik_group.proxmox[each.key].id
  order  = 10
}

resource "authentik_policy_binding" "proxmox-access" {
  target = authentik_application.proxmox.uuid
  group  = authentik_group.proxmox-users.id
  order  = 10
}
