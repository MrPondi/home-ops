resource "authentik_user" "ldap-bind" {
  username = "ldapservice"
  name     = "LDAP Outpost Bind User Service-Account"
  path     = "goauthentik.io"
  type     = "service_account"
}

resource "authentik_rbac_role" "ldap-search" {
  name     = "LDAP search"
}

output "rbac_user" {
  value = "You need to manually assign the role ${authentik_rbac_role.ldap-search.name} to the user ${authentik_user.ldap-bind.username} in the Authentik UI"
}

resource "authentik_group" "ldap-search" {
  name     = "ldapsearch"
  users    = [authentik_user.ldap-bind.id]
}

resource "authentik_stage_password" "ldap-authentication-password" {
  name     = "ldap-authentication-password"
  backends = ["authentik.core.auth.InbuiltBackend"]
}

resource "authentik_stage_identification" "ldap-identification-stage" {
  name           = "ldap-identification-stage"
  user_fields    = ["username", "email"]
  password_stage = authentik_stage_password.ldap-authentication-password.id
}

resource "authentik_stage_user_login" "ldap-authentication-login" {
  name = "ldap-authentication-login"
}

resource "authentik_outpost" "ldap" {
  name = "LDAP Outpost"
  protocol_providers = [authentik_provider_ldap.duo.id]
  service_connection = data.authentik_service_connection_kubernetes.local.id
  type = "ldap"
}