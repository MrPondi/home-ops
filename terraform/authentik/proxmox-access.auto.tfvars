# Shared with terraform/proxmox via symlink (../authentik/proxmox-access.auto.tfvars).
# Key = authentik entitlement on the Proxmox app = PVE group "<key>-authentik".
#   group: authentik group granting the entitlement (child of "Proxmox Users")
#   path/role: PVE ACL granted to the PVE group
# "admins" (Proxmox Admins -> Administrator on /) is static in code.
proxmox_access = {
  # vm-3001 = { group = "Proxmox VM 3001", path = "/vms/3001", role = "PVEVMUser" }
}
