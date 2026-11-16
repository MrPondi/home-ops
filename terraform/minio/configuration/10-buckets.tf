# Buckets on the QNAP MinIO (AIStor). prevent_destroy guards against a plan that
# would drop backups or the Terraform state itself.

locals {
  buckets = toset([
    "backups",         # cloudnative-pg/ (barman WAL + base), mariadb/ (physical backups)
    "kopiur",          # kopia repository for PVC snapshots
    "kritika-cache",   # kritika gateway download cache
    "pelican-backups", # pelican panel backups
    "terraform-state", # Terraform remote state (authentik, minio, proxmox)
  ])
}

resource "minio_s3_bucket" "this" {
  for_each = local.buckets

  bucket = each.key

  lifecycle {
    prevent_destroy = true
  }
}
