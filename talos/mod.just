set quiet
set script-interpreter := ['bash', '-euo', 'pipefail']
set shell := ['bash', '-euo', 'pipefail', '-c']

controller := `talosctl config info -o yaml | yq -e '.endpoints[0]'`

[private]
default:
    just -l talos

[confirm('Apply Talos config to ' + node + ' [y|N] ?')]
[doc('Apply Talos config to a node')]
apply-node node *args:
    talhelper gencommand apply --node "{{ node }}" --extra-flags "{{ args }}" | bash

[doc('Download Talos machine image')]
[script]
download-image version="" node=controller:
    if [ -z {{ version }} ]; then
        export VERSION="$(yq '.talosVersion' {{ source_directory() }}/talenv.yaml)"
    else
        export VERSION="{{ version }}"
    fi
    export SCHEMATIC="$(just talos gen-schematic-id true {{ node }})"
    curl -fL --remove-on-error --retry 5 --retry-delay 5 --retry-all-errors --progress-bar \
        -o "{{ source_directory() }}/talos-${VERSION}-${SCHEMATIC:0:8}.iso" \
        "https://factory.talos.dev/image/${SCHEMATIC}/${VERSION}/nocloud-amd64.iso"
    just log info "Downloaded Talos" version "${VERSION}" schematic "${SCHEMATIC}"

[doc('Generate Talos machine image link')]
[script]
get-image version="" node=controller:
    if [ -z {{ version }} ]; then
        export VERSION="$(yq '.talosVersion' {{ source_directory() }}/talenv.yaml)"
    else
        export VERSION="{{ version }}"
    fi
    export SCHEMATIC="$(just talos gen-schematic-id true {{ node }})"
    echo "https://factory.talos.dev/image/${SCHEMATIC}/${VERSION}/nocloud-amd64.iso"

[doc('Generate config for Talos cluster')]
gen-config:
    talhelper genconfig

[doc('Generate schematic ID from Talos schematic')]
gen-schematic-id iso="false" ip=controller:
    curl -sX POST --data-binary @<(just template "{{ source_directory() }}/schematic.yaml.j2" -D iso={{ iso }} -D ip={{ ip }}) "https://factory.talos.dev/schematics" | jq -r '.id'

[confirm('Reboot node ' + node + ' [y|N] ?')]
[doc('Reboot a node')]
reboot-node node:
    talosctl -n {{ node }} reboot -m powercycle

[confirm('Shutdown node ' + node + ' [y|N] ?')]
[doc('Shutdown a node')]
shutdown-node node *args:
    talosctl -n "{{ node }}" shutdown --force {{ args }}

[confirm('Upgrade node ' + node + ' [y|N] ?')]
[doc('Upgrade Talos version on a node')]
upgrade-node node *args:
    talosctl -n "{{ node }}" upgrade -i "$(just talos machine-image {{ node }})" -m powercycle --timeout=10m {{ args }}

[confirm('Upgrade Kubernetes [y|N] ?')]
[doc('Upgrade Kubernetes version on the cluster')]
[script]
upgrade-k8s version="":
    if [ -z {{ version }} ]; then
        version=$(yq '.kubernetesVersion' {{ source_directory() }}/talenv.yaml)
    else
        version='{{ version }}'
    fi
    talosctl -n "{{ controller }}" upgrade-k8s --to $version

[confirm('Reset node ' + node + ' [y|N] ?')]
[doc('Reset a node')]
reset-node node *args:
    talosctl -n "{{ node }}" reset --system-labels-to-wipe STATE --system-labels-to-wipe EPHEMERAL --system-labels-to-wipe u-local-hostpath --graceful=false {{ args }}

[confirm('Reset cluster [y|N] ?')]
[doc('Reset the entire cluster')]
reset-cluster:
    talhelper gencommand reset --extra-flags="--reboot --system-labels-to-wipe STATE --system-labels-to-wipe EPHEMERAL --graceful=false --wait=false" | bash

[private]
machine-controller node:
    yq '.nodes[] | select(.ipAddress == "{{ node }}") | .controlPlane // false' {{ source_directory() }}/talconfig.yaml

[private]
machine-image node:
    echo "$(yq '.nodes[] | select(.ipAddress == "{{ node }}") | .talosImageURL' {{ source_directory() }}/talconfig.yaml):$(yq '.talosVersion' {{ source_directory() }}/talenv.yaml)"
