locals {
  access_keys = {
    cloudnative-pg = {
      target_user = minio_iam_user.svc-homelab.name
      policy      = "cloudnative-pg.json"
    }
    kopiur = {
      target_user = minio_iam_user.svc-homelab.name
      policy      = "kopiur.json"
    }
    kritika-cache = {
      name = "Kritika cache"
      target_user = minio_iam_user.svc-homelab.name
      policy      = "kritika-cache.json"
    }
    mariadb = {
      target_user = minio_iam_user.svc-homelab.name
      policy      = "mariadb.json"
    }
    mcp = {
      name = "Minio MCP"
      target_user = minio_iam_user.svc-homelab.name
      policy      = "mcp.json"
    }
    pelican = {
      target_user = minio_iam_user.svc-homelab.name
      policy      = "pelican.json"
    }
    terraform = {
      name = "Terraform"
      target_user = minio_iam_user.svc-homelab.name
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
