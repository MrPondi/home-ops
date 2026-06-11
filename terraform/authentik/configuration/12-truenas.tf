resource "authentik_application" "truenas" {
  name              = "truenas"
  slug              = "truenas"
  protocol_provider = 0
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/truenas.svg"
  meta_launch_url   = "https://truenas.pondi.dev"
  open_in_new_tab   = true
}

resource "authentik_group" "truenas-users" {
  name         = "Truenas Users"
}

# resource "authentik_group" "truenas-admins" {
#   name         = "Truenas Admins"
#   parents      = [authentik_group.truenas-users.id]
# }

resource "authentik_policy_binding" "truenas-access" {
  target = authentik_application.truenas.uuid
  group  = authentik_group.truenas-users.id
  order  = 10
}

resource "authentik_policy_binding" "truenas-ldap-search-access" {
  target = authentik_application.truenas.uuid
  group  = authentik_group.ldap-search.id
  order  = 0
}