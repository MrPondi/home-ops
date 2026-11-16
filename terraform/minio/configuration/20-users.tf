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
