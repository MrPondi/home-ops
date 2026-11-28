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

variable "proxmox_access" {
  description = "PVE group \"<key>-authentik\" ACLs, granted via authentik."
  default     = {}
  type = map(object({
    group = optional(string)
    path  = string
    role  = string
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
      length(distinct(concat(["Proxmox Admins"], [for v in values(var.proxmox_access) : v.group if v.group != null])))
      == length([for v in values(var.proxmox_access) : v.group if v.group != null]) + 1
    )
    error_message = "Each group must be unique (\"Proxmox Admins\" is reserved)."
  }
}
