set default-list
set default-script
set quiet
set script-interpreter := ['bash', '-euo', 'pipefail']
set shell := ['bash', '-euo', 'pipefail', '-c']

[doc('Apply local Flux Kustomization')]
apply-ks ns ks:
    just kube render-local-ks "{{ ns }}" "{{ ks }}" | kubectl apply --server-side --field-manager=kustomize-controller -f -

[doc('Browse a PVC')]
browse-pvc ns claim:
    kubectl run -n {{ ns }} browse-pvc-{{ claim }} -it --rm --restart=Never \
        --image=mirror.gcr.io/alpine:latest \
        --overrides='{"spec":{"containers":[{"name":"browse-pvc-{{ claim }}","image":"mirror.gcr.io/alpine:latest","stdin":true,"tty":true,"command":["/bin/sh"],"workingDir":"/mnt","volumeMounts":[{"mountPath":"/mnt","name":"data"}]}],"volumes":[{"name":"data","persistentVolumeClaim":{"claimName":"{{ claim }}"}}]}}'

[doc('Delete local Flux Kustomization')]
delete-ks ns ks:
    just kube render-local-ks "{{ ns }}" "{{ ks }}" | kubectl delete -f -

[doc('Open a shell on a node')]
node-shell node:
    kubectl debug node/{{ node }} -n default -it --image="mirror.gcr.io/ubuntu:latest" --profile sysadmin
    name=$(kubectl get pods -n default --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}')
    if [[ $name == node-debugger-{{ node }}* ]]; then
        kubectl delete pod -n default $name
    else
        echo "Pod name '$name' does not start with 'node-debugger-{{ node }}', skipping deletion"
    fi

[doc('Prune pods in Failed, Pending, or Succeeded state')]
prune-pods:
    for phase in Failed Pending Succeeded; do
        kubectl delete pods -A --field-selector status.phase="$phase" --ignore-not-found=true
    done

[arg('resource', pattern='hr|ks|gitrepo|ocirepo|es|ps')]
[doc('Sync a resource')]
sync resource namespace="" name="":
    GET_ARGS="{{ name }}"

    if [ -n "{{ namespace }}" ]; then
        GET_ARGS="$GET_ARGS -n {{ namespace }}"
    else
        GET_ARGS="$GET_ARGS -A"
    fi

    kubectl get {{ resource }} $GET_ARGS -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name --no-headers | while read -r ns name _; do
        kubectl -n "$ns" annotate --field-manager flux-client-side-apply --overwrite {{ resource }} "$name" \
            "force-sync=$(date +%s)" \
            "reconcile.fluxcd.io/requestedAt=$(date +%s)" \
            "reconcile.fluxcd.io/forceAt=$(date +%s)"
    done

[doc('View a secret')]
view-secret ns secret="":
    kubectl view-secret -n {{ ns }} {{ secret }}

[private]
render-local-ks ns ks:
    flate build ks --namespace "{{ ns }}" --path "{{ justfile_directory() }}/kubernetes" --output yaml  --allow-missing-secrets "{{ ks }}"

[private]
hubble-ensure:
    if hubble status >/dev/null 2>&1; then
        exit 0
    fi
    nohup cilium hubble port-forward >/dev/null 2>&1 &
    for _ in $(seq 1 30); do
        if hubble status >/dev/null 2>&1; then
            exit 0
        fi
        sleep 1
    done
    echo "hubble relay unreachable - 'cilium hubble port-forward' failed to become ready" >&2
    exit 1

# Compact flow formatter: time | verdict | drop reason | source | destination | :port | dns query.
# Replies are hidden; drops mode keeps only POLICY_* drops. Pitfalls baked in: .flow? guard,
# --unbuffered, paren-wrapped select conditions.

[doc('Hubble relay status (starts the port-forward when needed)')]
hubble-status: hubble-ensure
    hubble status

[doc('Follow live flows')]
hubble-flows ns="" *args: hubble-ensure
    trap 'exit 0' INT TERM
    ns_args=""
    if [[ -n "{{ ns }}" ]]; then
        ns_args="--namespace {{ ns }}"
    fi
    hubble observe --follow -o json $ns_args {{ args }} 2>/dev/null \
        | jq --unbuffered -r '
            .flow? // empty
            | select(.is_reply != true)
            | [
                (.time | sub("^\\d{4}-\\d{2}-\\d{2}T"; "") | sub("\\..*"; "")),
                .verdict,
                (if .verdict == "DROPPED" then (.drop_reason_desc // "-") else "-" end),
                (if .source.pod_name then "\(.source.namespace)/\(.source.pod_name)" elif .source.IP then .source.IP else "reserved:\(.source.identity // "?")" end),
                (if .destination.pod_name then "\(.destination.namespace)/\(.destination.pod_name)" elif .destination.IP then .destination.IP else "reserved:\(.destination.identity // "?")" end),
                ((.l4.TCP.destination_port // .l4.UDP.destination_port // null) | if . == null then "-" else ":\(.)" end),
                (.l7.dns.query // "-")
              ]
            | @tsv'

[doc('Follow policy drops only (POLICY_DENIED)')]
hubble-drops ns="" *args: hubble-ensure
    trap 'exit 0' INT TERM
    ns_args=""
    if [[ -n "{{ ns }}" ]]; then
        ns_args="--namespace {{ ns }}"
    fi
    hubble observe --follow -o json $ns_args {{ args }} 2>/dev/null \
        | jq --unbuffered -r '
            .flow? // empty
            | select(.is_reply != true)
            | select(.verdict == "DROPPED" and ((.drop_reason_desc // "") | test("POLICY")))
            | [
                (.time | sub("^\\d{4}-\\d{2}-\\d{2}T"; "") | sub("\\..*"; "")),
                (.source.pod_name // .source.IP // "reserved:\(.source.identity // "?")"),
                (.destination.pod_name // .destination.IP // "reserved:\(.destination.identity // "?")"),
                ((.l4.TCP.destination_port // .l4.UDP.destination_port // null) | if . == null then "-" else ":\(.)" end),
                (.l7.dns.query // "-")
              ]
            | @tsv'

[doc('Bounded flow capture to an auto-named file (NS optional, SECONDS = duration, FILE = optional path override)')]
hubble-capture ns="" seconds="60" file="": hubble-ensure
    ns_args=""
    if [[ -n "{{ ns }}" ]]; then
        ns_args="--namespace {{ ns }}"
    fi
    file="{{ file }}"
    if [[ -z "$file" ]]; then
        scope="{{ ns }}"
        [[ -z "$scope" ]] && scope="all"
        file="/tmp/hubble-${scope}-$(date +%Y%m%d-%H%M%S).tsv"
    fi
    timeout "{{ seconds }}" hubble observe --follow -o json $ns_args 2>/dev/null \
        | jq --unbuffered -r '
            .flow? // empty
            | select(.is_reply != true)
            | [
                (.time | sub("^\\d{4}-\\d{2}-\\d{2}T"; "") | sub("\\..*"; "")),
                .verdict,
                (if .verdict == "DROPPED" then (.drop_reason_desc // "-") else "-" end),
                (if .source.pod_name then "\(.source.namespace)/\(.source.pod_name)" elif .source.IP then .source.IP else "reserved:\(.source.identity // "?")" end),
                (if .destination.pod_name then "\(.destination.namespace)/\(.destination.pod_name)" elif .destination.IP then .destination.IP else "reserved:\(.destination.identity // "?")" end),
                ((.l4.TCP.destination_port // .l4.UDP.destination_port // null) | if . == null then "-" else ":\(.)" end),
                (.l7.dns.query // "-")
              ]
            | @tsv' > "$file" || true
    gum log -t rfc3339 -s -l info "captured $(wc -l < "$file") flows -> $file"

[doc('Trigger an immediate CNPG base backup for a cluster (plugin method)')]
pg-initial-backup ns app:
    kubectl apply -n "{{ ns }}" -f - <<EOF
    apiVersion: postgresql.cnpg.io/v1
    kind: Backup
    metadata:
      name: {{ app }}-initial
    spec:
      cluster:
        name: {{ app }}
      method: plugin
      pluginConfiguration:
        name: barman-cloud.cloudnative-pg.io
    EOF
