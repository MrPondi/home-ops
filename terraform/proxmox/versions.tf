terraform {
  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "0.111.1"
    }
    bitwarden-secrets = {
      source  = "bitwarden/bitwarden-secrets"
      version = "1.0.0"
    }
    sops = {
      source  = "carlpett/sops"
      version = "1.4.1"
    }
  }
}