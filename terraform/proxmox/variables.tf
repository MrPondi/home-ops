variable "proxmox_access" {
  description = "Proxmox access levels: authentik entitlement/group and PVE group ACL (see proxmox-access.auto.tfvars)."
  type = map(object({
    group = string
    path  = string
    role  = string
  }))

  validation {
    condition     = alltrue([for k in keys(var.proxmox_access) : can(regex("^[A-Za-z0-9._-]+$", k))])
    error_message = "Keys become PVE group names and must match [A-Za-z0-9._-]+."
  }

  validation {
    condition     = contains(keys(var.proxmox_access), "admins")
    error_message = "The \"admins\" entry is required (authentik Admins inherits it)."
  }

  validation {
    condition     = length(distinct([for v in values(var.proxmox_access) : v.group])) == length(var.proxmox_access)
    error_message = "Each entry needs a unique authentik group name."
  }
}
