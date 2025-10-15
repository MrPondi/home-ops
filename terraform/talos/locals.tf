locals {
  # Storage and network settings from variables
  network_bridge   = var.network_bridge
  disk_storage     = var.disk_storage
  additional_disk_storage = var.additional_disk_storage

  # Transform nodes from variables for use in resources
  all_nodes_transformed = {
    for node in var.nodes : node.name => {
      vmid                    = node.vmid
      node                    = node.node
      name                    = node.name
      sockets                 = 1
      cpu_type                = "host"
      cores                   = node.cores
      memory                  = node.memory
      memory_balloon          = 0
      disk_type               = "scsi"
      disk_size               = node.disk_size
      disk_storage            = local.disk_storage
      additional_disk_size    = lookup(node, "additional_disk_size", null)
      additional_disk_storage = lookup(node, "additional_disk_size", null) != null ? local.additional_disk_storage : null
      onboot                  = true
      bios                    = "seabios"
      boot_order              = ["scsi0", "ide2"]
      network_bridge          = local.network_bridge
      network_model           = "virtio"
      mac_address             = node.mac_address
      tags                    = lookup(node, "tags", [node.role])
      role                    = node.role
      iso_file                = node.iso_file
      pci_devices             = lookup(node, "pci_devices", [])
    }
  }

  # Node type configurations for different roles
  node_configs = {
    controlplane = {
      description = "Talos Control Plane Node - Managed by Terraform"
    }
    worker = {
      description = "Talos Worker Node - Managed by Terraform"
    }
    "worker-gpu" = {
      description = "Talos GPU Worker Node - Managed by Terraform"
    }
  }
}