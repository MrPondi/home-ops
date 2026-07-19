locals {
    node_name = "orion"
}

resource "proxmox_download_file" "talos-orion" {
  content_type       = "iso"
  datastore_id       = "local"
  file_name          = "talos-orion.img"
  node_name          = local.node_name
  url                = "https://factory.talos.dev/image/1187564bfca177b9386718afb882b29c8390f58451858ff64f3ceb63ea016dff/1.13.4/nocloud-amd64.iso"
}

resource "proxmox_virtual_environment_vm" "k8s-0" {
  name        = "k8s-0"
  description = "Talos Control Plane Node - Managed by Terraform"

  node_name = local.node_name
  vm_id     = 3000
  machine   = "q35"
  boot_order = ["scsi0", "ide2"]

  agent {
    enabled = true
  }

  cpu {
    cores        = 16
    type         = "host"
  }

  memory {
    dedicated = 40*1024
    floating  = 0
  }

  disk {
    datastore_id = "local-lvm"
    interface    = "scsi0"
    size         = 100
    ssd          = true
  }

  disk {
    datastore_id = "local-lvm"
    interface    = "scsi1"
    size         = 400
    ssd          = true
  }

  disk {
    datastore_id = "local-lvm"
    interface    = "scsi2"
    size         = 150
    ssd          = true
  }

  cdrom {
    interface = "ide2"
    file_id   = "local:iso/talos-orion.img"
  }

  network_device {
    bridge = "Kubernet"
    model  = "virtio"
    mac_address = "BC:24:11:68:28:1C"
  }

  network_device {
    bridge = "VPN"
    model  = "virtio"
    mac_address = "BC:24:11:80:CA:BE"
  }

  network_device {
    bridge = "IoT"
    model  = "virtio"
    mac_address = "BC:24:11:F7:74:38"
    disconnected = true
  }

  hostpci {
    device   = "hostpci0"
    id       = "0000:0a:00"
    pcie     = true
    rombar   = true
  }

  hostpci {
    device   = "hostpci1"
    id       = "0000:09:00"
    pcie     = true
    rombar   = true
  }

  usb {
    host = "10c4:ea60"
    usb3 = true
  }
}
