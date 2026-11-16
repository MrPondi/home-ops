terraform {
  backend "s3" {
    bucket = "terraform-state"
    key    = "minio/terraform.tfstate"
    region = "us-east-1"

    endpoints = {
      s3 = "http://10.0.25.25:9000"
    }

    use_path_style              = true
    skip_s3_checksum            = true
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
  }
}

data "sops_file" "secret" {
  source_file = "../secrets.sops.yaml"
}

provider "bitwarden-secrets" {
  api_url         = "https://vault.bitwarden.com/api"
  identity_url    = "https://vault.bitwarden.com/identity"
  access_token    = data.sops_file.secret.data["BITWARDEN_ACCESS_TOKEN"]
  organization_id = data.sops_file.secret.data["BITWARDEN_ORGANIZATION_ID"]
}

data "bitwarden-secrets_secret" "minio" {
  id = "bf6713b4-8ae0-4100-9208-b3dc00d6a8ae"
}

provider "minio" {
  minio_server   = "10.0.25.25:9000"
  minio_user     = jsondecode(data.bitwarden-secrets_secret.minio.value)["MINIO_ROOT_USER"]
  minio_password = jsondecode(data.bitwarden-secrets_secret.minio.value)["MINIO_ROOT_PASSWORD"]
  minio_ssl      = false
}

module "configuration" {
  source = "./configuration"
  providers = {
    minio = minio
  }
}
