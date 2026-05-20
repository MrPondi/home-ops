terraform {
  required_providers {
    authentik = {
      source  = "goauthentik/authentik"
    }
    bitwarden-secrets = {
      source = "registry.terraform.io/bitwarden/bitwarden-secrets"
      version = "1.0.0"
    }
    sops = {
      source = "carlpett/sops"
    }
  }
}