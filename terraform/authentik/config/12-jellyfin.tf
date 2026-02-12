resource "authentik_group" "users" {
  name         = "Jellyfin Users"
  # users        = [authentik_user.ldap-bind.id]
}

resource "authentik_group" "admins" {
  name         = "Jellyfin Admins"
  # users        = [authentik_user.ldap-bind.id]
}

resource "authentik_application" "jellyfin" {
  name              = "Jellyfin"
  slug              = "jellyfin"
  protocol_provider = authentik_provider_ldap.duo.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/jellyfin.svg"
  meta_launch_url   = "https://jellyfin.pondi.dev"
  open_in_new_tab   = true
}