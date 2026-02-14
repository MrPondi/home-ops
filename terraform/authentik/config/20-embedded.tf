resource "authentik_outpost" "embedded" {
  name = "authentik Embedded Outpost"

  protocol_providers = [
    authentik_provider_proxy.radarr.id,
    authentik_provider_proxy.sonarr.id,
    authentik_provider_proxy.prowlarr.id,
    authentik_provider_proxy.bazarr.id,
    authentik_provider_proxy.qbittorrent.id,
    authentik_provider_proxy.zwavejs2mqtt.id,
  ]
}
