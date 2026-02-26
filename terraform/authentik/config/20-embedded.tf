resource "authentik_outpost" "embedded" {
  name = "authentik Embedded Outpost"

  protocol_providers = [
    authentik_provider_proxy.radarr.id,
    authentik_provider_proxy.sonarr.id,
    authentik_provider_proxy.prowlarr.id,
    authentik_provider_proxy.bazarr.id,
    authentik_provider_proxy.qbittorrent.id,
    authentik_provider_proxy.zwavejs2mqtt.id,
    authentik_provider_proxy.prometheus.id,
    authentik_provider_proxy.alertmanager.id,
    authentik_provider_proxy.victoria-logs.id,
  ]
}

resource "authentik_group" "admins" {
  name = "authentik Admins"
  is_superuser = true

  parents = [
    authentik_group.pelican-access.id,
    authentik_group.grafana-admins.id,
    authentik_group.hass-admins.id,
    authentik_group.jellyfin-admins.id,
    authentik_group.minio-admins.id,
    authentik_group.nextcloud-admins.id,
    authentik_group.torrent-mgmt.id,
    authentik_group.flux-operator-admins.id,
    authentik_group.metrics-access.id
  ]
}