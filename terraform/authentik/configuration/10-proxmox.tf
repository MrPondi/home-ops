data "bitwarden-secrets_secret" "proxmox" {
  id = "b2579e58-9838-4556-b613-b3ee0000fa21"
}

# PVE groups granted by RAC endpoint access (bindings managed on the endpoint, e.g. per user
# in the UI); keys match proxmox-access.auto.tfvars. Every other key is an app entitlement.
locals {
  proxmox-rac-endpoints = {
    game0         = authentik_rac_endpoint.game0.id
    game1         = authentik_rac_endpoint.game1.id
    pelican-wings = authentik_rac_endpoint.pelican-wings0.id
  }
}

# RAC check mirrors authentik's endpoint listing: app policies, then endpoint policies.
resource "authentik_property_mapping_provider_scope" "proxmox" {
  name       = "Proxmox Groups"
  scope_name = "proxmox"
  expression = <<EOF
from authentik.core.models import Application
from authentik.policies.engine import PolicyEngine
from authentik.providers.rac.models import Endpoint

app = Application.objects.get(slug="proxmox")
proxmox_groups = {e.name for e in request.user.app_entitlements(app)}

rac_groups = ${jsonencode({ for k, v in local.proxmox-rac-endpoints : v => k })}
for endpoint in Endpoint.objects.filter(pk__in=rac_groups.keys()).select_related("provider"):
    app_engine = PolicyEngine(endpoint.provider.application, request.user, request.http_request)
    app_engine.build()
    if not app_engine.passing:
        continue
    engine = PolicyEngine(endpoint, request.user, request.http_request)
    engine.build()
    if engine.passing:
        proxmox_groups.add(rac_groups[str(endpoint.pk)])

return {"proxmox_groups": sorted(proxmox_groups)}
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

resource "authentik_group" "proxmox-users" {
  name = "Proxmox Users"
}

resource "authentik_group" "proxmox-admins" {
  name    = "Proxmox Admins"
  parents = [authentik_group.proxmox-users.id]
}

resource "authentik_application_entitlement" "proxmox-admins" {
  name        = "admins"
  application = authentik_application.proxmox.uuid
}

resource "authentik_policy_binding" "proxmox-admins-entitlement" {
  target = authentik_application_entitlement.proxmox-admins.id
  group  = authentik_group.proxmox-admins.id
  order  = 10
}

resource "authentik_group" "proxmox" {
  for_each = { for k, v in var.proxmox_access : k => v if v.group != null && !contains(keys(local.proxmox-rac-endpoints), k) }

  name    = each.value.group
  parents = [authentik_group.proxmox-users.id]
}

resource "authentik_application_entitlement" "proxmox" {
  for_each = { for k, v in var.proxmox_access : k => v if !contains(keys(local.proxmox-rac-endpoints), k) }

  name        = each.key
  application = authentik_application.proxmox.uuid
}

resource "authentik_policy_binding" "proxmox-entitlement" {
  for_each = authentik_group.proxmox

  target = authentik_application_entitlement.proxmox[each.key].id
  group  = each.value.id
  order  = 10
}

resource "authentik_policy_binding" "proxmox-access" {
  target = authentik_application.proxmox.uuid
  group  = authentik_group.proxmox-users.id
  order  = 10
}

resource "authentik_policy_expression" "proxmox-entitled" {
  name       = "proxmox-entitled"
  expression = <<EOF
from authentik.providers.oauth2.models import ScopeMapping

mapping = ScopeMapping.objects.get(pk="${authentik_property_mapping_provider_scope.proxmox.id}")
return bool(mapping.evaluate(request.user, request.http_request)["proxmox_groups"])
EOF
}

resource "authentik_policy_binding" "proxmox-entitled" {
  target = authentik_application.proxmox.uuid
  policy = authentik_policy_expression.proxmox-entitled.id
  order  = 20
}
