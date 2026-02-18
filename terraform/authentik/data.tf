# Flows

data "authentik_flow" "default-provider-authorization-explicit-consent" {
  slug = "default-provider-authorization-explicit-consent"
}

data "authentik_flow" "default-provider-authorization-implicit-consent" {
  slug = "default-provider-authorization-implicit-consent"
}

data "authentik_flow" "default-invalidation-flow" {
  slug = "default-invalidation-flow"
}

data "authentik_flow" "default-provider-invalidation-flow" {
  slug = "default-provider-invalidation-flow"
}

# OAuth2/OIDC scopes

data "authentik_property_mapping_provider_scope" "scope-email" {
  name = "authentik default OAuth Mapping: OpenID 'email'"
}

data "authentik_property_mapping_provider_scope" "scope-openid" {
  name = "authentik default OAuth Mapping: OpenID 'openid'"
}

data "authentik_property_mapping_provider_scope" "scope-profile" {
  name = "authentik default OAuth Mapping: OpenID 'profile'"
}

# SAML scopes

data "authentik_property_mapping_provider_saml" "saml-email" {
  name = "authentik default SAML Mapping: Email"
}

data "authentik_property_mapping_provider_saml" "saml-groups" {
  name = "authentik default SAML Mapping: Groups"
}

data "authentik_property_mapping_provider_saml" "saml-name" {
  name = "authentik default SAML Mapping: Name"
}

data "authentik_property_mapping_provider_saml" "saml-upn" {
  name = "authentik default SAML Mapping: UPN"
}

data "authentik_property_mapping_provider_saml" "saml-user-id" {
  name = "authentik default SAML Mapping: User ID"
}

data "authentik_property_mapping_provider_saml" "saml-username" {
  name = "authentik default SAML Mapping: Username"
}

data "authentik_property_mapping_provider_saml" "saml-windows-accountname" {
  name = "authentik default SAML Mapping: WindowsAccountname (Username)"
}

# Certificates

data "authentik_certificate_key_pair" "self-signed" {
  name = "authentik Self-signed Certificate"
}

# Service Connection

data "authentik_service_connection_kubernetes" "local" {
  name = "Local Kubernetes Cluster"
}

# Users

data "authentik_group" "admins" {
  name = "authentik Admins"
}