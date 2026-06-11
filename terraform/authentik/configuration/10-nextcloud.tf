resource "authentik_property_mapping_provider_scope" "nextcloud-profile" {
  name       = "Nextcloud Profile"
  scope_name = "nextcloud"
  expression = <<EOF
# Extract all groups the user is a member of
groups = [group.name.removeprefix("nextcloud-") for group in request.user.ak_groups.all() if group.name.startswith("nextcloud-")]
quota = request.user.group_attributes().get("nextcloud_quota")

return {
    "name": request.user.name,
    "nc-groups": groups,
    "quota": quota * 1024 * 1024 * 1024 if quota is not None else None, # Convert GB to Bytes
    "avatar": request.user.avatar,
    "is_admin": request.user.is_superuser or ak_is_group_member(request.user, name="Nextcloud Admins"),
    # Since attribute 'birthdate' is supported from NC version 30 onwards, this attribute can be mapped too. Accepted format: YYYY-MM-DD
    "birthdate": user.attributes.get("nextcloud_birthdate", None),
}
EOF
}

data "bitwarden-secrets_secret" "nextcloud" {
  id = "49b2348d-2176-4241-9a0a-b3e90116ac4e"
}

resource "authentik_provider_oauth2" "nextcloud" {
  name          = "Nextcloud OAuth2 Provider"
  client_id     = jsondecode(data.bitwarden-secrets_secret.nextcloud.value)["NEXTCLOUD_OIDC_CLIENT_ID"]
  client_secret = jsondecode(data.bitwarden-secrets_secret.nextcloud.value)["NEXTCLOUD_OIDC_CLIENT_SECRET"]

  authorization_flow  = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id

  allowed_redirect_uris = [
    {
      matching_mode = "strict",
      redirect_uri_type = "authorization",
      url           = "https://nextcloud.pondi.dev/apps/oidc_login/oidc",
    }
  ]

  property_mappings = [
    authentik_property_mapping_provider_scope.nextcloud-profile.id,
    data.authentik_property_mapping_provider_scope.scope-email.id,
    data.authentik_property_mapping_provider_scope.scope-openid.id,
    data.authentik_property_mapping_provider_scope.scope-profile.id,
  ]

  signing_key = data.authentik_certificate_key_pair.self-signed.id
  sub_mode = "user_uuid"
}

resource "authentik_application" "nextcloud" {
  name              = "nextcloud"
  slug              = "nextcloud"
  protocol_provider = authentik_provider_oauth2.nextcloud.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/nextcloud.svg"
  meta_launch_url   = "https://nextcloud.pondi.dev"
  open_in_new_tab   = true
}

resource "authentik_group" "nextcloud-users" {
  name         = "Nextcloud Users"
}

resource "authentik_group" "nextcloud-admins" {
  name         = "Nextcloud Admins"
  parents      = [authentik_group.nextcloud-users.id]
}

resource "authentik_policy_binding" "nextcloud-access" {
  target = authentik_application.nextcloud.uuid
  group  = authentik_group.nextcloud-users.id
  order  = 10
}