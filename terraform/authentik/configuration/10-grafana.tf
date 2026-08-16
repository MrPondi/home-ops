data "bitwarden-secrets_secret" "grafana" {
  id = "fd76020c-90ae-4d8e-b515-b3dc00d3e903"
}

resource "authentik_group" "grafana-viewers" {
  name    = "Grafana Viewers"
}

resource "authentik_group" "grafana-editors" {
  name    = "Grafana Editors"
  parents = [authentik_group.grafana-viewers.id]
}

resource "authentik_group" "grafana-admins" {
  name    = "Grafana Admins"
  parents = [authentik_group.grafana-editors.id]
}

resource "authentik_provider_oauth2" "grafana" {
  name          = "Grafana OAuth2 Provider"
  client_id     = jsondecode(data.bitwarden-secrets_secret.grafana.value)["GRAFANA_OIDC_CLIENT_ID"]
  client_secret = jsondecode(data.bitwarden-secrets_secret.grafana.value)["GRAFANA_OIDC_CLIENT_SECRET"]

  authorization_flow  = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id

  allowed_redirect_uris = [
    {
      matching_mode = "strict",
      redirect_uri_type = "authorization",
      url           = "https://grafana.pondi.dev/login/generic_oauth",
    }
  ]

  logout_method = "frontchannel"
  logout_uri    = "https://grafana.pondi.dev/logout"

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
    data.authentik_property_mapping_provider_scope.scope-email.id,
    data.authentik_property_mapping_provider_scope.scope-openid.id,
    data.authentik_property_mapping_provider_scope.scope-profile.id,
  ]

  signing_key = data.authentik_certificate_key_pair.self-signed.id
}

resource "authentik_application" "grafana" {
  name              = "Grafana"
  slug              = "grafana"
  protocol_provider = authentik_provider_oauth2.grafana.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/grafana.svg"
  meta_launch_url   = "https://grafana.pondi.dev"
  open_in_new_tab   = true
}

resource "authentik_policy_binding" "grafana-access" {
  target = authentik_application.grafana.uuid
  group  = authentik_group.grafana-viewers.id
  order  = 10
}