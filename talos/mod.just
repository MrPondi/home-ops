set quiet := true
set shell := ['bash', '-euo', 'pipefail', '-c']

talos_dir := justfile_dir() + '/talos'
controller := `talosctl config info -o yaml | yq -e '.endpoints[0]'`

[private]
default:
    just -l talos

[doc('Apply Talos config to a node')]
apply-node node *args:
    talhelper gencommand apply --node "{{ node }}" --extra-flags "{{ args }}"

[doc('Download Talos machine image')]
download-image version schematic:
    gum spin --title "Downloading Talos {{ version }} ..." -- \
    curl -sfL --remove-on-error --retry 5 --retry-delay 5 --retry-all-errors \
        -o "{{ talos_dir }}/talos-{{ version }}-{{ replace_regex(schematic, '^(.{8}).*', '$1') }}.iso" \
        "https://factory.talos.dev/image/{{ schematic }}/{{ version }}/nocloud-amd64.iso"
    just log info "Downloaded Talos" version "{{ version }}" schematic "{{ schematic }}"

[doc('Generate config for Talos cluster')]
gen-config:
    talhelper genconfig &>/dev/null

[doc('Generate kubeconfig for Talos cluster')]
gen-kubeconfig:
    talosctl kubeconfig -n "{{ controller }}" -f --force-context-name main {{ justfile_dir() }}

[doc('Generate schematic ID from Talos schematic')]
gen-schematic-id:
    curl -sX POST --data-binary "@{{ talos_dir }}/schematic.yaml" "https://factory.talos.dev/schematics" | jq -r '.id'

[doc('Reboot a node')]
reboot-node node:
    gum confirm "Reboot node {{ node }}?" --default="No" && \
        talosctl -n {{ node }} reboot -m powercycle || exit 0

[doc('Reset a node')]
reset-node node:
    gum confirm "Reset node {{ node }}?" --default="No" && \
        talosctl -n "{{ node }}" reset --graceful=false || exit 0

[doc('Shutdown a node')]
shutdown-node node:
    gum confirm "Shutdown node {{ node }}?" --default="No" && \
        talosctl -n "{{ node }}" shutdown --force || exit 0

[doc('Upgrade Kubernetes version on the cluster')]
upgrade-k8s version="":
    if [ -z {{ version }} ]; then \
        version=$(yq '.kubernetesVersion' {{ talos_dir }}/talenv.yaml); \
    else \
        version='{{ version }}'; \
    fi; \
    talosctl -n "{{ controller }}" upgrade-k8s --to $version

[doc('Upgrade Talos version on a node')]
upgrade-node node:
    talosctl -n "{{ node }}" upgrade -i "$(just talos machine-image {{ node }})" -m powercycle --timeout=10m

[private]
machine-controller node:
    yq '.nodes[] | select(.ipAddress == "{{ node }}") | .controlPlane // false' {{ talos_dir }}/talconfig.yaml

[private]
machine-image node:
    echo "$(yq '.nodes[] | select(.ipAddress == "{{ node }}") | .talosImageURL' {{ talos_dir }}/talconfig.yaml):$(yq '.talosVersion' {{ talos_dir }}/talenv.yaml)"
