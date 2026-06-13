data "bitwarden-secrets_secret" "pelican-wings0" {
  id = "36f92b01-d742-45da-b595-b3fd003a4136"
}

resource "authentik_property_mapping_provider_rac" "pelican-wings-ssh-username" {
  name = "Pelican Wings SSH Username Mapping"
  settings = jsonencode({
    "username": "ubuntu"
  })

}

resource "authentik_provider_rac" "pelican-wings" {
    name = "Pelican Wings RAC Provider"
    authorization_flow  = data.authentik_flow.default-provider-authorization-implicit-consent.id
    connection_expiry = "hours=2"
    property_mappings = [
        authentik_property_mapping_provider_rac.pelican-wings-ssh-username.id,
    ]
}

resource "authentik_rac_endpoint" "pelican-wings0" {
    name = "Pelican Wings0 RAC Endpoint"
    host = "wings0.pondi.dev"
    protocol = "ssh"
    protocol_provider = authentik_provider_rac.pelican-wings.id
    maximum_connections = -1
    settings = jsonencode({
        "private-key": data.bitwarden-secrets_secret.pelican-wings0.value,
    })
}

resource "authentik_application" "pelican-wings" {
  name              = "Pelican Wings"
  slug              = "pelican-wings"
  protocol_provider = authentik_provider_rac.pelican-wings.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/docker-moby.svg"
}

resource "authentik_group" "pelican-wings-ssh" {
  name         = "Pelican Wings SSH Access"
  parents      = [authentik_group.pelican-access.id]
}

resource "authentik_policy_binding" "pelican-wings-ssh" {
  target = authentik_application.pelican-wings.uuid
  group  = authentik_group.pelican-wings-ssh.id
  order  = 10
}