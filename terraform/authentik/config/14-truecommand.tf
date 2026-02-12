resource "authentik_property_mapping_provider_saml" "saml-truecommand-username" {
  name       = "TrueCommand SAML Username Mapping"
  saml_name  = "unique_name"
  expression = "return request.user.username"
}

resource "authentik_property_mapping_provider_saml" "saml-truecommand-email" {
  name       = "TrueCommand SAML Email Mapping"
  saml_name  = "email"
  expression = "return request.user.email"
}

resource "authentik_property_mapping_provider_saml" "saml-truecommand-display-name" {
  name       = "TrueCommand SAML Display Name Mapping"
  saml_name  = "display_name"
  expression = "return request.user.name"
}

resource "authentik_provider_saml" "truecommand" {
  name          = "TrueCommand SAML Provider"
  acs_url       = "https://truecommand.pondi.dev/saml/acs"
  issuer        = "truecommand-saml"
  sp_binding    = "post"

  authorization_flow  = data.authentik_flow.default-provider-authorization-implicit-consent.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id

  name_id_mapping   = authentik_property_mapping_provider_saml.saml-truecommand-email.id
  property_mappings = [
    data.authentik_property_mapping_provider_saml.saml-email.id,
    data.authentik_property_mapping_provider_saml.saml-groups.id,
    data.authentik_property_mapping_provider_saml.saml-name.id,
    data.authentik_property_mapping_provider_saml.saml-upn.id,
    data.authentik_property_mapping_provider_saml.saml-user-id.id,
    data.authentik_property_mapping_provider_saml.saml-username.id,
    data.authentik_property_mapping_provider_saml.saml-windows-accountname.id,
    authentik_property_mapping_provider_saml.saml-truecommand-username.id,
    authentik_property_mapping_provider_saml.saml-truecommand-email.id,
    authentik_property_mapping_provider_saml.saml-truecommand-display-name.id,
  ]

  signing_kp = data.authentik_certificate_key_pair.self-signed.id
}

resource "authentik_application" "truecommand" {
  name              = "TrueCommand"
  slug              = "truecommand"
  protocol_provider = authentik_provider_saml.truecommand.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/truecommand.svg"
  meta_launch_url   = "https://truecommand.pondi.dev"
  open_in_new_tab   = true
}