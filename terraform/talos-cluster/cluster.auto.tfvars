# Primary system disk datastore id (Proxmox storage ID)
# Choices visible on node: e.g. local, local-zfs, zfs1, zfs2, zfs3
disk_storage = "local-lvm"

# Datastore for additional data disks (if nodes define additional_disk_size)
additional_disk_storage = "local-lvm"

# Proxmox network bridge
network_bridge = "Kubernet"

# Define the cluster nodes
nodes = [
  # Control Plane Node
  {
    name = "k8s-01",
    node = "orion",
    vmid = 3000,
    iso_file = "local:iso/talos-orion01.img",
    role = "controlplane",
    mac_address = "BC:24:11:68:28:1C",
    cores = 16,
    memory = 1024*32,
    disk_size = "50G",
    additional_disk_size = "400G",
    pci_devices = [ {
      id       = "0000:01:00.0"
      rom_file = "vbios_9955hx.bin"
    }, {
      id       = "0000:01:00.1"
    }]
  }
]