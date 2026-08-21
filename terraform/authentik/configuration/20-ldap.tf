resource "authentik_flow" "duo-ldap-authentication-flow" {
  name        = "Duo LDAP Authentication Flow"
  title       = "Duo LDAP Authentication Flow"
  slug        = "duo-ldap-authentication-flow"
  designation = "authentication"
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

resource "authentik_stage_authenticator_validate" "ldap-duo-mfa" {
  name                  = "ldap-duo-mfa-validation"
  device_classes        = ["duo"]
  not_configured_action = "skip"
}

resource "authentik_stage_user_login" "ldap-authentication-login" {
  name = "ldap-authentication-login"
}

resource "authentik_flow_stage_binding" "duo-ldap-identification-stage" {
  target = authentik_flow.duo-ldap-authentication-flow.uuid
  stage  = authentik_stage_identification.ldap-identification-stage.id
  order  = 10
}

resource "authentik_flow_stage_binding" "duo-ldap-mfa" {
  target = authentik_flow.duo-ldap-authentication-flow.uuid
  stage  = authentik_stage_authenticator_validate.ldap-duo-mfa.id
  policy_engine_mode = "all"
  evaluate_on_plan = false
  re_evaluate_policies = true
  order  = 20
}

resource "authentik_policy_binding" "ldapservice-bypass" {
  target = authentik_flow_stage_binding.duo-ldap-mfa.id
  user  = authentik_user.ldap-bind.id
  failure_result = true
  negate = true
  order  = 10
}

resource "authentik_policy_binding" "ip-bypass" {
  target = authentik_flow_stage_binding.duo-ldap-mfa.id
  policy  = authentik_policy_expression.local-ip-check.id
  failure_result = true
  negate = true
  order  = 20
}

resource "authentik_flow_stage_binding" "duo-ldap-authentication-login" {
  target = authentik_flow.duo-ldap-authentication-flow.uuid
  stage  = authentik_stage_user_login.ldap-authentication-login.id
  order  = 30
}

resource "authentik_provider_ldap" "duo" {
  name        = "Duo LDAP Provider"
  base_dn     = "dc=ldap-duo,dc=pondi,dc=dev"
  bind_flow   = authentik_flow.duo-ldap-authentication-flow.uuid
  unbind_flow = data.authentik_flow.default-invalidation-flow.id
}

resource "authentik_user" "ldap-bind" {
  username = "ldapservice"
  name     = "LDAP Outpost Bind User Service-Account"
  path     = "goauthentik.io"
  type     = "service_account"
}

resource "authentik_rbac_role" "ldap-search" {
  name     = "LDAP search"
}

resource "authentik_group" "ldap-search" {
  name     = "ldapsearch"
  users    = [authentik_user.ldap-bind.id]
  roles    = [authentik_rbac_role.ldap-search.id]
}

resource "authentik_rbac_permission_role" "duo-provider-search" {
  role       = authentik_rbac_role.ldap-search.id
  model      = "authentik_providers_ldap.ldapprovider"
  permission = "authentik_providers_ldap.search_full_directory"
  object_id  = authentik_provider_ldap.duo.id
}

resource "authentik_outpost" "ldap" {
  name               = "LDAP Outpost"
  protocol_providers = [authentik_provider_ldap.duo.id]
  service_connection = data.authentik_service_connection_kubernetes.local.id
  type               = "ldap"
  config = jsonencode({
    "log_level": "info",
    "refresh_interval": "minutes=5",
    "authentik_host": "https://auth.pondi.dev/",
    "authentik_host_browser": "",
    "object_naming_template": "ak-outpost-%(name)s",
    "kubernetes_replicas": 1,
    "kubernetes_namespace": "security",
    "authentik_host_insecure": false,
    "kubernetes_service_type": "LoadBalancer",
    "kubernetes_disabled_components": ["ingress", "httproute"],
    "kubernetes_json_patches": {
      "service": [
        {
          "op"   : "add",
          "path" : "/metadata/annotations",
          "value": {}
        },
        {
          "op"   : "add",
          "path" : "/metadata/annotations/external-dns.kubernetes.io~1hostname",
          "value": "ldap.pondi.dev"
        },
        {
          "op"   : "add",
          "path" : "/metadata/annotations/lbipam.cilium.io~1ips",
          "value": "10.0.30.133"
        },
        {
          "op"   : "add",
          "path" : "/metadata/annotations/gatus.home-operations.com~1endpoint",
          "value": "name: ldap outpost\ngroup: services"
        },
        {
          "op"   : "add",
          "path" : "/spec/externalTrafficPolicy",
          "value": "Local"
        }
      ]
    },
  })
}