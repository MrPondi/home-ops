resource "authentik_provider_rac" "games" {
  name               = "Games RAC Provider"
  authorization_flow = data.authentik_flow.default-provider-authorization-implicit-consent.id
  connection_expiry  = "hours=6"
}

resource "authentik_rac_endpoint" "game0" {
  name                = "Game0"
  host                = "10.0.20.199:5900"
  protocol            = "vnc"
  protocol_provider   = authentik_provider_rac.games.id
  maximum_connections = -1
  settings = jsonencode({
      "read-only": "true",
  })
}

resource "authentik_application" "game-vnc" {
  name              = "Game VNC"
  slug              = "game-vnc"
  protocol_provider = authentik_provider_rac.games.id
  meta_icon         = "https://api.iconify.design/fluent-emoji-flat/video-game.svg?height=none"
}

resource "authentik_group" "games-vnc" {
  name = "Games VNC Access"
}

resource "authentik_policy_binding" "games-vnc" {
  target = authentik_application.game-vnc.uuid
  group  = authentik_group.games-vnc.id
  order  = 10
}
