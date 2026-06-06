terraform {
  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "0.108.0"
    }
    sops = {
      source = "carlpett/sops"
    }
  }
}

data "sops_file" "secret" {
  source_file = "../secret.sops.json"
}


provider "proxmox" {
  endpoint  = "https://pve.internal:8006"
  api_token = data.sops_file.secret.data["PROXMOX_TOKEN"]
  insecure  = true
  ssh {
    agent = true
    username = "root"
    private_key = base64decode(data.sops_file.secret.data["PROXMOX_SSH_KEY"])
  }
}

resource "proxmox_virtual_environment_vm" "vm" {
  for_each = local.all_nodes_transformed

  name        = each.value.name
  node_name   = each.value.node
  description = local.node_configs[each.value.role].description
  tags        = each.value.tags
  vm_id       = each.value.vmid

  started = each.value.onboot
  bios    = each.value.bios
  machine = "q35"

  # Enable QEMU Guest Agent for better VM management
  agent {
    enabled = true
  }

  # Boot the disk first, then the ISO as fallback
  boot_order = each.value.boot_order

  cpu {
    cores   = each.value.cores
    sockets = each.value.sockets
    type    = each.value.cpu_type
  }

  memory {
    dedicated = each.value.memory
    floating  = each.value.memory_balloon
  }

  # Network configuration
  network_device {
    bridge      = each.value.network_bridge
    model       = each.value.network_model
    mac_address = each.value.mac_address
  }

  # Primary disk
  disk {
    interface    = "scsi0"
    datastore_id = each.value.disk_storage
    size         = tonumber(trimsuffix(each.value.disk_size, "G"))
    cache        = "none"
    discard      = "ignore"
    ssd          = true
  }

  # Additional disk for storage (worker nodes with additional_disk_size)
  dynamic "disk" {
    for_each = each.value.additional_disk_size != null ? [1] : []
    content {
      interface    = "scsi1"
      datastore_id = each.value.additional_disk_storage
      size         = tonumber(trimsuffix(each.value.additional_disk_size, "G"))
      cache        = "none"
      discard      = "ignore"
      ssd          = true
    }
  }
  # Attach appropriate Talos ISO based on node role
  cdrom {
    interface = "ide2"
    file_id   = each.value.iso_file
  }

  # PCI device passthrough
  dynamic "hostpci" {
    for_each = { for idx, device in each.value.pci_devices : idx => device }
    content {
      device   = "hostpci${hostpci.key}"
      id       = hostpci.value.id
      pcie     = true
      rombar   = true
      rom_file = hostpci.value.rom_file
    }
  }
}

# resource "proxmox_virtual_environment_download_file" "talos-orion01" {
#   content_type = "iso"
#   datastore_id = "local"
#   file_name    = "talos-orion01.img"
#   node_name    = "orion"
#   url          = "https://factory.talos.dev/image/bfcdcc4aefa30b2da7014993374109c98a0c2e9cc8a54ba1c01923eb7c8abe17/v1.11.1/nocloud-amd64.iso"
# }

output "vm_mac_addresses" {
  description = "MAC addresses of the created VMs."
  value = {
    for k, v in proxmox_virtual_environment_vm.vm : k => v.network_device[0].mac_address
  }
}

output "vm_details" {
  description = "Details of created VMs organized by role."
  value = {
    for k, v in proxmox_virtual_environment_vm.vm : k => {
      vmid        = v.vm_id
      mac_address = v.network_device[0].mac_address
      role        = local.all_nodes_transformed[k].role
      cores       = v.cpu[0].cores
      memory      = v.memory[0].dedicated
      iso_used    = local.all_nodes_transformed[k].iso_file
    }
  }
}

output "node_roles" {
  description = "Node roles and their configurations."
  value = {
    controlplane = [for k, v in local.all_nodes_transformed : k if v.role == "controlplane"]
    workers      = [for k, v in local.all_nodes_transformed : k if v.role == "worker"]
    gpu_workers  = [for k, v in local.all_nodes_transformed : k if v.role == "worker-gpu"]
  }
}
