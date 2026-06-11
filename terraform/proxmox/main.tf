data "sops_file" "secret" {
  source_file = "../secrets.sops.yaml"
}

provider "bitwarden-secrets" {
  api_url         = "https://vault.bitwarden.com/api"
  identity_url    = "https://vault.bitwarden.com/identity"
  access_token    = data.sops_file.secret.data["BITWARDEN_ACCESS_TOKEN"]
  organization_id = data.sops_file.secret.data["BITWARDEN_ORGANIZATION_ID"]
}

data "bitwarden-secrets_secret" "proxmox" {
  id = "b2579e58-9838-4556-b613-b3ee0000fa21"
}

provider "proxmox" {
  endpoint  = "https://pve.internal:8006"
  api_token = jsondecode(data.bitwarden-secrets_secret.proxmox.value)["PROXMOX_TERRAFORM_TOKEN"]
  insecure  = true
  ssh {
    agent = true
    username = "root"
    private_key = data.sops_file.secret.data["PROXMOX_SSH_KEY"]
  }
}

module "configuration" {
  source = "./configuration"
  providers = {
    proxmox           = proxmox
    bitwarden-secrets = bitwarden-secrets
  }
}
