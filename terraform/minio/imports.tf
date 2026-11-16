# One-time adoption of the objects that already existed before this module.
# Safe to keep (no-op once in state) or delete after the first apply.

import {
  for_each = toset(["backups", "kopiur", "kritika-cache", "pelican-backups", "terraform-state"])
  to       = module.configuration.minio_s3_bucket.this[each.key]
  id       = each.key
}

import {
  to = module.configuration.minio_iam_user.svc-homelab
  id = "svc-homelab"
}

import {
  to = module.configuration.minio_iam_user_policy_attachment.svc-homelab-readwrite
  id = "svc-homelab/readwrite"
}

import {
  for_each = {
    cloudnative-pg = "csTqUpjZOpqmDPINYh1J"
    kopiur         = "RGzLtwsGquLhcMREYZD4"
    kritika-cache  = "3UIp8B8mWjqzH78QJiE7"
    mariadb        = "js9fITQ1YEOMJ9tUWG5I"
    mcp            = "aYuZbNCMb8F6qmzTkadu"
    pelican        = "HCsVjLQVgNoRRdO8Bgzh"
    terraform      = "XUKi3TRbcG8TvNJGOfvB"
  }
  to = module.configuration.minio_iam_service_account.this[each.key]
  id = each.value
}
