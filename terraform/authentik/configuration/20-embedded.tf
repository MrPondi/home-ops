data "bitwarden-secrets_secret" "kopiur" {
  id = "3c1222b8-e303-4f0b-9734-b48d00ba7def"
}

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
    authentik_group.ai-admins.id
  ]

  attributes = jsonencode({
    "KOPIUR_WEBUI_USERNAME": jsondecode(data.bitwarden-secrets_secret.kopiur.value)["WEBUI_USERNAME"],
    "KOPIUR_WEBUI_PASSWORD": jsondecode(data.bitwarden-secrets_secret.kopiur.value)["WEBUI_PASSWORD"]
  })
}