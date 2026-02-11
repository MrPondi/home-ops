terraform {
  required_providers {
    authentik = {
      source  = "goauthentik/authentik"
    }
    bitwarden-secrets = {
      source = "registry.terraform.io/bitwarden/bitwarden-secrets"
      version = "0.5.4-pre"
    }
    sops = {
      source = "carlpett/sops"
    }
  }
}