resource "authentik_group" "jellyfin-users" {
  name         = "Jellyfin Users"
}

resource "authentik_group" "jellyfin-admins" {
  name         = "Jellyfin Admins"
  parents      = [authentik_group.jellyfin-users.id]
}

resource "authentik_application" "jellyfin" {
  name              = "Jellyfin"
  slug              = "jellyfin"
  protocol_provider = authentik_provider_ldap.duo.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/jellyfin.svg"
  meta_launch_url   = "https://jellyfin.pondi.dev"
  open_in_new_tab   = true
}

resource "authentik_policy_binding" "jellyfin-access" {
  target = authentik_application.jellyfin.uuid
  group  = authentik_group.jellyfin-users.id
  order  = 10
}

resource "authentik_policy_binding" "jellyfin-ldap-search-access" {
  target = authentik_application.jellyfin.uuid
  group  = authentik_group.ldap-search.id
  order  = 0
}