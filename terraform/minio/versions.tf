terraform {
  required_providers {
    minio = {
      source  = "aminueza/minio"
      version = "3.46.4"
    }
    bitwarden-secrets = {
      source  = "bitwarden/bitwarden-secrets"
      version = "1.0.1"
    }
    sops = {
      source  = "carlpett/sops"
      version = "1.4.1"
    }
  }
}
