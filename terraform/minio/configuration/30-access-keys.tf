# Access keys (service accounts) with explicit, scoped policies.
#
# The secret halves live in Bitwarden and reach the cluster via ExternalSecrets;
# Terraform never sets them, so existing keys keep their values. MinIO generates
# the access key ID on create, so after a full MinIO rebuild every recreated key
# gets a new ID + secret that must be copied back into its Bitwarden item.
#
# Changing target_user forces a replacement (= new key), so move a key between
# owners by hand (delete + recreate with the same values), then re-import.

locals {
  access_keys = {
    # name => owner + policy file; consumers in comments
    cloudnative-pg = {
      # Bitwarden item cloudnative-pg -> every CNPG cluster's <app>-s3 secret
      target_user = minio_iam_user.svc-homelab.name
      policy      = "cloudnative-pg.json"
    }
    kopiur = {
      # Bitwarden item kopiur -> kopiur-repository-secret (components/kopiur/base)
      target_user = minio_iam_user.svc-homelab.name
      policy      = "kopiur.json"
    }
    kritika-cache = {
      name = "Kritika cache"
      # Bitwarden item kritika -> kritika-system/kritika-cache
      target_user = minio_iam_user.svc-homelab.name
      policy      = "kritika-cache.json"
    }
    mariadb = {
      # Bitwarden item mariadb -> database/mariadb-secret
      target_user = minio_iam_user.svc-homelab.name
      policy      = "mariadb.json"
    }
    mcp = {
      name = "Minio MCP"
      # Bitwarden item minio (MINIO_MCP_*) -> ai/toolhive-minio-secret (read-only)
      target_user = minio_iam_user.svc-homelab.name
      policy      = "mcp.json"
    }
    pelican = {
      # Bitwarden item pelican -> default/pelican-secret
      target_user = minio_iam_user.svc-homelab.name
      policy      = "pelican.json"
    }
    terraform = {
      name = "Terraform"
      # Terraform S3 backend credentials (local env). Still owned by the akadmin
      # OpenID identity; move it to svc-homelab by hand, then update this.
      target_user = "Opu6ipPyD6CGVfNIU7MgVLuck1qcRl0PDXnxhx-cGw4"
      policy      = "terraform.json"
    }
  }
}

resource "minio_iam_service_account" "this" {
  for_each = local.access_keys

  target_user = each.value.target_user
  name        = try(each.value.name, each.key)
  policy      = jsonencode(jsondecode(file("${path.module}/policies/${each.value.policy}")))

  lifecycle {
    prevent_destroy = true
  }
}
