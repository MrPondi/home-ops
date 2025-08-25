import pulumi_proxmoxve as proxmox

import pulumi

config = pulumi.Config()

talos_nodes = {
    "cp": {
        "target_nodes": ["orion"],  # "cassiopeia", "pegasus"],
        "resources": {"memory": 8 * 1024, "cpus": 4, "disk": 100},
    },
    "worker": {
        "target_nodes": ["orion"],  # "cassiopeia", "pegasus"],
        "resources": {"memory": 16 * 1024, "cpus": 8, "disk": 250},
    },
}


control_planes = []
workers = []
for type in talos_nodes:
    for id, node in enumerate(talos_nodes[type]["target_nodes"], start=1):
        vm = proxmox.vm.VirtualMachine(
            resource_name=f"k8s-{node}-{type}{id:02d}",
            name=f"k8s-{node}-{type}{id:02d}",
            agent=proxmox.vm.VirtualMachineAgentArgs(enabled=True),
            node_name=node,
            vm_id=2999 + id if type == "cp" else 3009 + id,
            cpu=proxmox.vm.VirtualMachineCpuArgs(
                cores=talos_nodes[type]["resources"]["cpus"],
                type="x86-64-v2-AES",
                units=100,
            ),
            boot_orders=["scsi0", "ide2"],
            disks=[
                proxmox.vm.VirtualMachineDiskArgs(
                    interface="scsi0",
                    datastore_id="local-lvm",
                    size=talos_nodes[type]["resources"]["disk"],
                    ssd=True,
                )
            ],
            cdrom=proxmox.vm.VirtualMachineCdromArgs(
                file_id="local:iso/talos-nocloud-amd64.iso", interface="ide2"
            ),
            scsi_hardware="virtio-scsi-pci",
            memory=proxmox.vm.VirtualMachineMemoryArgs(
                dedicated=talos_nodes[type]["resources"]["memory"],
                floating=talos_nodes[type]["resources"]["memory"],
            ),
            network_devices=[
                proxmox.vm.VirtualMachineNetworkDeviceArgs(
                    bridge="Kubernet", model="virtio", firewall=False
                ),
                proxmox.vm.VirtualMachineNetworkDeviceArgs(
                    bridge="DMZ", model="virtio", firewall=False
                ),
            ],
            operating_system=proxmox.vm.VirtualMachineOperatingSystemArgs(type="l26"),
            started=False,
        )
        if type == "cp":
            control_planes.append(vm)
        else:
            workers.append(vm)

# Export VM names to verify
pulumi.export("control_planes", [vm.name for vm in control_planes])
pulumi.export("workers", [vm.name for vm in workers])
