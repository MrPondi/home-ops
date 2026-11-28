# Shared with terraform/proxmox via symlink (../authentik/proxmox-access.auto.tfvars).
# Key = PVE group "<key>-authentik" (sent in the proxmox_groups claim).
#   path/role: PVE ACL granted to the PVE group
#   group (optional): create this authentik group and grant it the key as an app entitlement;
#                     omit it to bind users/groups to the entitlement in the authentik UI.
# Keys in local.proxmox-rac-endpoints (terraform/authentik 10-proxmox.tf) are granted to whoever
# can open that RAC endpoint instead (no entitlement); "admins" is static in code.
proxmox_access = {
  game0         = { path = "/vms/152", role = "PVEVMUser" } # roblox-lxc, RAC Game0
  game1         = { path = "/vms/151", role = "PVEVMUser" } # roblox-lxc2, RAC Game1
  pelican-wings = { path = "/vms/102", role = "PVEVMUser" } # Docker (wings0), RAC Pelican Wings0
}
