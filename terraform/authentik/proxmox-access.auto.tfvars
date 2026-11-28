# Shared with terraform/proxmox via symlink (../authentik/proxmox-access.auto.tfvars).
# Key = authentik entitlement on the Proxmox app = PVE group "<key>-authentik".
#   group: authentik group granting the entitlement (child of "Proxmox Users")
#   path/role: PVE ACL granted to the PVE group
proxmox_access = {
  admins = {
    group = "Proxmox Admins"
    path  = "/"
    role  = "Administrator"
  }
}
