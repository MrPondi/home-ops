# Game VMs over RAC (VNC). One app/provider, one endpoint per VM.
#
# Access is two-layered:
#   1. App: members of "Games Access" (assign in the authentik UI) see the Games tile.
#   2. Endpoint: each VM carries one Roblox account, so bind ONE user per endpoint in the UI
#      (Applications > Providers > Games RAC Provider > Endpoints > <vm> > Bindings).
#      Terraform deliberately declares no endpoint bindings, so UI-made ones are never
#      overwritten. An endpoint with no binding is open to every "Games Access" member.
#
# Do not rename an endpoint's resource address without a `moved` block: destroy+create
# drops its UI bindings.

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
