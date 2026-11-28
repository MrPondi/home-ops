terraform {
  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "0.124.0"
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
# Shared with the other stack via proxmox-access.auto.tfvars (symlinked). "admins" is static.
variable "proxmox_access" {
  description = "Extra Proxmox access levels: key = authentik entitlement = PVE group \"<key>-authentik\"."
  default     = {}
  type = map(object({
    group = string # authentik group (child of "Proxmox Users")
    path  = string # PVE ACL path, e.g. /vms/3001 or /pool/<name>
    role  = string # PVE role, e.g. PVEVMUser
  }))

  validation {
    condition     = alltrue([for k in keys(var.proxmox_access) : can(regex("^[A-Za-z0-9._-]+$", k))])
    error_message = "Keys become PVE group names and must match [A-Za-z0-9._-]+."
  }

  validation {
    condition     = !contains(keys(var.proxmox_access), "admins")
    error_message = "\"admins\" is a static entry managed in code, not in tfvars."
  }

  validation {
    condition = (
      length(distinct(concat(["Proxmox Admins"], [for v in values(var.proxmox_access) : v.group])))
      == length(var.proxmox_access) + 1
    )
    error_message = "Each entry needs a unique authentik group name (\"Proxmox Admins\" is reserved)."
  }
}
