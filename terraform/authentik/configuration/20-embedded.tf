resource "authentik_group" "admins" {
  name = "authentik Admins"
  is_superuser = true

  parents = [
    authentik_group.grafana-admins.id,
    authentik_group.hass-admins.id,
    authentik_group.jellyfin-admins.id,
    authentik_group.minio-admins.id,
    authentik_group.nextcloud-admins.id,
    authentik_group.torrent-mgmt.id,
    authentik_group.flux-operator-admins.id,
    authentik_group.metrics-access.id,
    authentik_group.pelican-wings-ssh.id,
  ]
}