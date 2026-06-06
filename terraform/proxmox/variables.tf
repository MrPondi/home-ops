variable "nodes" {
  description = "A list of virtual machines to create."
  type = list(object({
    name                 = string
    node                 = string
    vmid                 = number
    iso_file             = string
    role                 = string
    mac_address          = string
    cores                = number
    memory               = number
    disk_size            = string
    tags                 = optional(list(string))
    additional_disk_size = optional(string)
    additional_disk_storage = optional(string, "datapool")
    pci_devices          = optional(list(object({
      id       = string
      rom_file = optional(string)
    })))
  }))
}

variable "disk_storage" {
  description = "Primary datastore ID for the main VM disk (e.g. local, local-zfs, zfs1)"
  type        = string
}

variable "additional_disk_storage" {
  description = "Datastore ID for any additional data disks (if nodes specify additional_disk_size)."
  type        = string
  default     = "local"
}

variable "network_bridge" {
  description = "Proxmox bridge to attach VM NICs to (e.g. vmbr0)."
  type        = string
  default     = "vmbr0"
}
