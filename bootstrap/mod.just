set positional-arguments := true
set quiet := true
set shell := ['bash', '-euo', 'pipefail', '-c']

bootstrap_dir := justfile_dir() + '/bootstrap'
kubernetes_dir := justfile_dir() + '/kubernetes'
controller := `talosctl config info -o yaml | yq -e '.endpoints[0]'`
nodes := `talosctl config info -o yaml | yq -e '.nodes | join (" ")'`

[private]
default: talhelper talos kubernetes controller-kubeconfig wait namespaces sops-secrets crds apps cilium-kubeconfig

[doc('Prepare talhelper')]
[working-directory('../talos')]
talhelper:
    just log info "Running stage..." "stage" "$0"
    if ! [ -f talsecret.sops.yaml ]; then \
        talhelper gensecret | sops --filename-override talos/talsecret.sops.yaml --encrypt /dev/stdin > talsecret.sops.yaml; \
    fi
    just talos gen-config

[doc('Install Talos')]
talos:
    just log info "Running stage..." "stage" "$0"
    for n in {{ nodes }}; do \
        if ! op=$(just talos apply-node "$n" --insecure 2>&1); then \
            if [[ "$op" == *"certificate required"* ]]; then \
                just log info "Talos already configured, skipping apply of config" "stage" "$0" "node" "$n"; \
                continue; \
            fi; \
            just log fatal "Failed to apply Talos configuration" "stage" "$0" "node" "$n" "output" "$op"; \
        fi; \
    done

[doc('Install Kubernetes')]
kubernetes:
    just log info "Running stage..." "stage" "$0"
    until op=$(talosctl -n "{{ controller }}" bootstrap 2>&1 || true) && [[ "$op" == *"AlreadyExists"* ]]; do \
        just log info "Kubernetes bootstrap in progress. Retrying in 5 seconds..." "stage" "$0"; \
        sleep 5; \
    done

[doc('Fetch kubeconfig with the controller endpoint')]
controller-kubeconfig:
    just log info "Running stage..." "stage" "$0"
    if ! just talos gen-kubeconfig; then \
        just log fatal "Failed to fetch kubeconfig" "stage" "$0"; \
    fi
    if ! kubectl config set-cluster main --server "https://{{ controller }}:6443"; then \
        just log fatal "Failed to set kubectl cluster server address" "stage" "$0"; \
    fi

[doc('Wait for nodes to be not-ready')]
wait:
    just log info "Running stage..." "stage" "$0"
    if ! kubectl wait nodes --for=condition=Ready=True --all --timeout=10s &>/dev/null; then \
        until kubectl wait nodes --for=condition=Ready=False --all --timeout=10s &>/dev/null; do \
            just log info "Nodes not available, waiting for nodes to be available. Retrying in 5 seconds..." "stage" "$0"; \
            sleep 5; \
        done \
    fi

[doc('Apply Kubernetes namespaces')]
namespaces:
    just log info "Running stage..." "stage" "$0"
    find "{{ kubernetes_dir }}/apps" -mindepth 1 -maxdepth 1 -type d -printf "%f\n" | while IFS= read -r ns; do \
        if ! kubectl create namespace "$ns" --dry-run=client -o yaml | kubectl apply --server-side -f -; then \
            just log fatal "Failed to apply namespace" "stage" "$0" "namespace" "$ns"; \
        fi; \
    done

[doc('Apply Kubernetes resources')]
resources:
    just log info "Running stage..." "stage" "$0"
    if ! just template "{{ bootstrap_dir }}/resources.yaml.j2" | kubectl apply --server-side -f -; then \
        just log fatal "Failed to apply resources" "stage" "$0"; \
    fi

[doc('Apply Sops secrets')]
sops-secrets:
    just log info "Running stage..." "stage" "$0"

    secrets=( \
    "{{ justfile_directory() }}/bootstrap/github-deploy-key.sops.yaml" \
    "{{ justfile_directory() }}/kubernetes/components/common/sops/cluster-secrets.sops.yaml" \
    "{{ justfile_directory() }}/kubernetes/components/common/sops/sops-age.sops.yaml" \
    ); \
    for secret in "${secrets[@]}"; do \
        resource_name=$(basename "$secret" ".sops.yaml"); \
        if sops exec-file "$secret" "kubectl --namespace flux-system diff --filename {}" &>/dev/null; then \
            just log info "Sops secret resource is up-to-date: $resource_name"; \
            continue; \
        fi; \
        if sops exec-file "$secret" "kubectl --namespace flux-system apply --server-side --filename {}" &>/dev/null; then \
            just log info "Sops secret resource applied successfully: $resource_name"; \
        else \
            just log fatal "Failed to apply sops secret resource: $resource_name" "stage" "$0"; \
            exit 1; \
        fi; \
    done

[doc('Apply Helmfile CRDs')]
crds:
    just log info "Running stage..." "stage" "$0"
    if ! crds=$(helmfile -f "{{ bootstrap_dir }}/helmfile.d/00-crds.yaml" template --quiet) || [[ -z "${crds}" ]]; then \
        just log fatal "Failed to render crds" "stage" "$0"; \
    fi; \
    if echo "${crds}" | kubectl diff -f - &>/dev/null; then \
        just log info "CRDs are up-to-date"; \
    else \
        if ! echo "${crds}" | kubectl apply --server-side -f -; then \
            just log fatal "Failed to apply crds" "stage" "$0"; \
        fi; \
    fi

[doc('Apply Helmfile Apps')]
apps:
    just log info "Running stage..." "stage" "$0"
    if ! helmfile -f "{{ bootstrap_dir }}/helmfile.d/01-apps.yaml" sync --hide-notes; then \
        just log fatal "Failed to sync helmfile" "stage" "$0"; \
    fi

[doc('Fetch kubeconfig with the cilium endpoint')]
cilium-kubeconfig:
    just log info "Running stage..." "stage" "$0"
    if ! just talos gen-kubeconfig; then \
        just log fatal "Failed to fetch kubeconfig" "stage" "$0"; \
    fi
