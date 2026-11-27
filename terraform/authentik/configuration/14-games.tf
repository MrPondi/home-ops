resource "authentik_provider_rac" "games" {
  name               = "Games RAC Provider"
  authorization_flow = data.authentik_flow.default-provider-authorization-implicit-consent.id
  connection_expiry  = "hours=6"
}

resource "authentik_rac_endpoint" "game0" {
  name                = "Game0"
  host                = "10.0.20.199"
  protocol            = "vnc"
  protocol_provider   = authentik_provider_rac.games.id
  maximum_connections = 1
}

resource "authentik_application" "games" {
  name              = "Games"
  slug              = "games"
  protocol_provider = authentik_provider_rac.games.id
  meta_icon         = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/roblox.svg"
}

resource "authentik_group" "games-access" {
  name = "Games Access"
}

resource "authentik_policy_binding" "games-access" {
  target = authentik_application.games.uuid
  group  = authentik_group.games-access.id
  order  = 10
}
