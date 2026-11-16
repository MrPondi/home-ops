# Internal service user that owns every machine access key. Nobody logs in as it:
# its password is random and unmanaged (reset it from the console if ever needed).
# Admins see/manage its keys under Identity -> Users -> svc-homelab.
# readwrite is the ceiling; each access key narrows it with its own policy.

resource "minio_iam_user" "svc-homelab" {
  name = "svc-homelab"

  lifecycle {
    prevent_destroy = true
    ignore_changes  = [secret]
  }
}

resource "minio_iam_user_policy_attachment" "svc-homelab-readwrite" {
  user_name   = minio_iam_user.svc-homelab.name
  policy_name = "readwrite"
}
