data "sops_file" "secret" {
  source_file = "../secrets.sops.yaml"
}

provider "bitwarden-secrets" {
  api_url         = "https://vault.bitwarden.com/api"
  identity_url    = "https://vault.bitwarden.com/identity"
  access_token    = data.sops_file.secret.data["BITWARDEN_ACCESS_TOKEN"]
  organization_id = data.sops_file.secret.data["BITWARDEN_ORGANIZATION_ID"]
}

data "bitwarden-secrets_secret" "authentik" {
  id = "b142d67e-b08e-4f1e-b48d-b3ea00ddd070"
}

provider "authentik" {
  url   = "https://auth.pondi.dev"
  token = jsondecode(data.bitwarden-secrets_secret.authentik.value)["AUTHENTIK_TERRAFORM_TOKEN"]
}

module "configuration" {
  source = "./configuration"
  providers = {
    authentik         = authentik
    bitwarden-secrets = bitwarden-secrets
  }
}
