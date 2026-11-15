---
name: add-app
description: Scaffold a new application for this repository's Flux layout
---

# Add New Application

This skill scaffolds a new application for this repository's Flux layout.
Repository-wide conventions live in `AGENTS.md` — read it first.

## Repository-specific assumptions

- App manifests live in `kubernetes/apps/<namespace>/<app>/`; `ks.yaml` sits at the app root, manifests for each Kustomization go in a subdir (default `app/`)
- The Namespace object comes from `kubernetes/apps/<namespace>/namespace.yaml` (placeholder `name: _`, renamed by the overlay kustomization's `namespace:` field). The `alerts` component (Flux notifications) is injected by the namespace overlay — never include it in the app itself
- The namespace overlay wires the `replacements` list (`kubernetes/components/replacements/ks.yaml`, via the overlay's top-level `replacements:` field) which stamps `spec.targetNamespace` onto every Kustomization from the overlay's Namespace object. The replacement is the default and the only mechanism — never set an explicit `targetNamespace` in `ks.yaml`
- Every app declares its own per-app `OCIRepository` in `ocirepository.yaml`; `app-template` apps point `spec.chartRef.name` at that per-app repo (named after the app). There is no shared/injected chart source
- Secrets use `external-secrets` with the `bitwarden-secretsmanager` `ClusterSecretStore`
- Fail-closed namespaces: see AGENTS.md › "Fail-closed namespaces" for the list and what the namespace `default-deny` already provides (DNS, kube-API egress, prometheus scrape ingress). A per-app `networkpolicy.yaml` is only needed for **app-specific routes** (envoy route ingress, cross-ns services, Postgres/Dragonfly, S3/internet/FQDN egress) and must **not** re-declare the inherited rules. In open namespaces (`network`, `kube-system`, `flux-system`, `longhorn-system`) do **not** scaffold a CNP unless it is complete (a CNP isolates its pods immediately)
- Postgres and Dragonfly are attached by **labels** on the Flux Kustomization (`components.postgres/enabled: "true"`, `components.dragonfly/enabled: "true"`, see AGENTS.md › "Label-driven components") — never add `components/postgres` or `components/dragonfly` to `spec.components` by hand. A labeled `ks.yaml` must carry `spec.components`, `spec.dependsOn` and `spec.healthCheckExprs` as lists (`[]` allowed)
- Kopiur backups: apps with a PVC to back up attach `../../../../components/kopiur/backup` via the Kustomization's `spec.components` (SnapshotPolicy + hourly SnapshotSchedule + Restore + PVC, all keyed on `${APP}`). Mover-job egress is handled namespace-wide by the overlay's `kopiur/base` component (the `kopiur-mover` CNP) — never hand-write mover rules; just confirm the overlay attaches `kopiur/base` and verify with `kubectl kopiur snapshot now -n <ns> --policy <app>` (hubble must show zero `POLICY_DENIED` from the mover pod)
- The root `flux-system` Kustomization already patches HelmRelease defaults (crds `CreateReplace`, rollback/upgrade remediation) — do not add them to the app

## Workflow

### Step 1: Collect application details

Ask the user (via your harness's question tool, e.g. `question` / `AskUserQuestion`) to gather:

1. App name
2. Namespace/category, such as `default`, `media`, or `ai`
3. Image repository
4. Image tag or digest
5. Primary service port
6. Whether the app needs an `ExternalSecret`
7. Whether the app needs persistence
8. Whether the app needs an ingress route (envoy-internal / envoy-external) — if yes, plan for gatus/homepage route annotations
9. Flux `dependsOn` entries for the Kustomization (usually `external-secrets-store` in namespace `external-secrets`)
10. Whether the app needs kopiur PVC backups (attach `components/kopiur/backup`; also confirm the namespace overlay attaches `kopiur/base`)
11. Whether the app needs Postgres and/or Dragonfly (label-driven components — see Repository-specific assumptions)

If the requested namespace does not exist under `kubernetes/apps/`, stop and ask the user how to proceed (new namespace = new overlay + `namespace.yaml`, possibly fail-closed).
Always ask for confirmation before writing files.

### Step 2: Inspect neighboring apps

Before generating files:

1. Read 1-2 existing apps in the same namespace (e.g. `bazarr` for `media`, `open-webui` for `ai`).
2. Match the local patterns for probes, persistence, routes, secret templates, and (in fail-closed namespaces) the CNP building blocks.
3. For CNP label values, render the would-be app (`kubectl kustomize`) or copy from a neighboring app — never guess chart labels.

### Step 3: Create the app directory

Create:

`kubernetes/apps/<namespace>/<app>/`

with `ks.yaml` (Step 5) and the manifest subdir:

`kubernetes/apps/<namespace>/<app>/app/`

containing at minimum:

- `helmrelease.yaml`
- `kustomization.yaml`
- `ocirepository.yaml`

Optionally create (only when needed):

- `networkpolicy.yaml` — in a fail-closed namespace only when the app has app-specific routes (route ingress, Postgres/Dragonfly, cross-ns/S3/internet egress); in an open namespace omit it (or make it complete: route ingress + full egress)
- `externalsecret.yaml`
- other app-specific manifests such as `configmap.yaml` or `pvc.yaml`

### Step 4: Generate the app manifests

#### `kubernetes/apps/<namespace>/<app>/app/kustomization.yaml`

```yaml
---
# yaml-language-server: $schema=https://json.schemastore.org/kustomization
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
    - ./helmrelease.yaml
    - ./ocirepository.yaml
```

Add `./networkpolicy.yaml` (when needed, see above), `./externalsecret.yaml`, and other resource files only when required. Follow the list ordering rules in AGENTS.md ("List ordering rules"): files in the kustomization's own directory come first (section 1, self-sorted), directory references last (section 4, self-sorted).

#### `kubernetes/apps/<namespace>/<app>/app/helmrelease.yaml`

```yaml
---
# yaml-language-server: $schema=https://raw.githubusercontent.com/bjw-s-labs/helm-charts/main/charts/other/app-template/schemas/helmrelease-helm-v2.schema.json
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
    name: <app>
spec:
    chartRef:
        kind: OCIRepository
        name: <app>
    interval: 1h
    values:
        controllers:
            <app>:
                annotations:
                    reloader.stakater.com/auto: "true"
                containers:
                    app:
                        image:
                            repository: <image-repository>
                            tag: <image-tag-or-digest>
                        env:
                            TZ: Europe/Warsaw
                            <APP_PORT_ENV>: &port <port>
                        probes:
                            # dominant local pattern: custom probe WITH a full httpGet.
                            # `custom: true` without spec.httpGet is invalid — when no
                            # endpoint is known, drop `custom` and let the chart synthesize.
                            liveness: &probe
                                enabled: true
                                custom: true
                                spec:
                                    httpGet:
                                        path: <liveness-path>
                                        port: *port
                                    periodSeconds: 30
                                    timeoutSeconds: 5
                                    failureThreshold: 5
                            readiness: *probe
                        resources:
                            requests:
                                cpu: 10m
                        securityContext:
                            allowPrivilegeEscalation: false
                            readOnlyRootFilesystem: true
                            capabilities: { drop: ["ALL"] }
        defaultPodOptions:
            securityContext:
                runAsNonRoot: true
                runAsGroup: 1000
                runAsUser: 1000
                fsGroup: 1000
                fsGroupChangePolicy: OnRootMismatch
        service:
            app:
                ports:
                    http:
                        port: *port
```

Adjust the template to match local patterns in the same namespace. The `&port` anchor lives on the container's port `env` var so the probe and service stay in sync (see `bazarr`, `sonarr`). A `custom` probe is only valid **with a full `spec.httpGet`** (path + port) — when no health endpoint is known, drop `custom` and let the chart synthesize the probe. Add `route` (envoy parentRefs, `hostnames: ["{{ .Release.Name }}.pondi.dev"]`, gatus/homepage annotations), `persistence`, `envFrom`, or extra manifests only when needed.

#### `kubernetes/apps/<namespace>/<app>/app/networkpolicy.yaml` (fail-closed namespaces, app-specific routes only)

Purely additive — DNS, kube-API egress and prometheus scrape ingress come from the namespace `default-deny` and must not be repeated. Example for a routed app (copy from `open-webui`):

```yaml
---
# yaml-language-server: $schema=https://k8s-schemas.home-operations.com/cilium.io/ciliumnetworkpolicy_v2.json
apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
    name: &name <app>
spec:
    endpointSelector:
        matchLabels:
            app.kubernetes.io/name: *name # copy from the rendered Deployment — do not guess
    ingress:
        # HTTPRoute <app>.pondi.dev (envoy-internal)
        - fromEndpoints:
              - matchLabels:
                    k8s:io.kubernetes.pod.namespace: network
                    k8s:app.kubernetes.io/name: envoy
                    k8s:gateway.envoyproxy.io/owning-gateway-name: envoy-internal
          toPorts:
              - ports:
                    - port: "<port>"
                      protocol: TCP
    # egress: add only app-specific targets (Postgres `cnpg.io/cluster: ${APP}` :5432, Dragonfly :6379, FQDN/internet)
```

Copy each additional building block (Postgres/Dragonfly egress, FQDN pairs, CIDR/internet) from a neighboring app's `networkpolicy.yaml` rather than retyping it from memory, and comment every rule with what it matches.

#### `kubernetes/apps/<namespace>/<app>/app/ocirepository.yaml`

For an `app-template` app, point at the shared chart with a per-app source named after the app:

```yaml
---
# yaml-language-server: $schema=https://k8s-schemas.home-operations.com/source.toolkit.fluxcd.io/ocirepository_v1.json
apiVersion: source.toolkit.fluxcd.io/v1
kind: OCIRepository
metadata:
    name: <app>
spec:
    interval: 15m
    layerSelector:
        mediaType: application/vnd.cncf.helm.chart.content.v1.tar+gzip
        operation: copy
    ref:
        tag: 5.1.0
    url: oci://ghcr.io/bjw-s-labs/helm/app-template
```

Use the `app-template` tag already pinned by neighboring apps (not a guessed newer version). For a non-`app-template` chart, set `url` and `ref.tag` to that chart's OCI source instead. `spec.chartRef.name` in the `HelmRelease` must match this `metadata.name`.

#### `kubernetes/apps/<namespace>/<app>/app/externalsecret.yaml`

```yaml
---
# yaml-language-server: $schema=https://k8s-schemas.home-operations.com/external-secrets.io/externalsecret_v1.json
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
    name: <app>
spec:
    secretStoreRef:
        kind: ClusterSecretStore
        name: bitwarden-secretsmanager
    target:
        name: <app>-secret
        template:
            data:
                <KEY>: "{{ .<KEY> }}"
    dataFrom:
        - extract:
              key: <app>
```

If the app needs templated secret data, mirror patterns from similar existing apps instead of forcing a generic template.

### Step 5: Generate the flux kustomization

Create:

`kubernetes/apps/<namespace>/<app>/ks.yaml`

Template:

```yaml
---
# yaml-language-server: $schema=https://k8s-schemas.home-operations.com/kustomize.toolkit.fluxcd.io/kustomization_v1.json
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
    name: &app <app>
spec:
    dependsOn:
        - name: external-secrets-store
          namespace: external-secrets
    interval: 1h
    path: ./kubernetes/apps/<namespace>/<app>/app
    postBuild:
        substitute:
            APP: *app
    prune: true
    sourceRef:
        kind: GitRepository
        name: flux-system
        namespace: flux-system
    wait: false
```

If the app needs `postBuild.substituteFrom` secrets, add `- name: <namespace>-postbuild` (e.g. `ai-postbuild`) first in `dependsOn` and its ExternalSecret under `kubernetes/apps/<namespace>/app-postbuild/secrets/` (see AGENTS.md › "Postbuild secrets"); the Kustomization name is namespace-prefixed because flate drops same-named Kustomizations across namespaces.

Drop `dependsOn` when the app has no secrets or external deps. For Postgres/Dragonfly add the `metadata.labels` entries (`components.postgres/enabled: "true"`, `components.dragonfly/enabled: "true"`) plus `components: []`/`healthCheckExprs: []` placeholders when absent — the root `flux-system` patch appends the component, operator `dependsOn` and health checks. Add other `components` (pointing at `../../../../components/...`) and `healthCheckExprs` only when the app needs them. Follow nearby `ks.yaml` files in the same namespace for exact patterns. `spec.targetNamespace` is stamped by the overlay's `replacements` list from the Namespace object — never set it in `ks.yaml`.

### Step 6: Update the namespace overlay

Update:

`kubernetes/apps/<namespace>/kustomization.yaml`

Add:

```yaml
resources:
    - ./<app>/ks.yaml
```

Follow the list ordering rules in AGENTS.md ("List ordering rules"): `./namespace.yaml` (section 1) first, then the `./<app>/ks.yaml` Kustomization entries (section 3, self-sorted).

### Step 7: Verify

Verify that:

1. `kubernetes/apps/<namespace>/<app>/` contains `ks.yaml` and the `app/` subdir with `helmrelease.yaml`, `kustomization.yaml`, `ocirepository.yaml` (plus `networkpolicy.yaml`/`externalsecret.yaml` when applicable).
2. The overlay kustomization lists `./<app>/ks.yaml` and the app's kustomization lists every created file.
3. `ks.yaml` omits `targetNamespace` (stamped by the overlay replacement), sets `postBuild.substitute.APP`, and its `path` points at the right subdir.
4. The app has its own `ocirepository.yaml` (named after the app), and the HelmRelease's `spec.chartRef.name` matches it.
5. In a fail-closed namespace the CNP only adds app-specific routes (no DNS/kube-API/scrape rules); no partial CNP was added in an open namespace.
6. Render cleanly: `mise run //kubernetes:render-local-ks <ns> <app>` (or `kubectl kustomize <dir>` before the overlay entry is added), and `uv run scripts/kustomization_order_audit.py` + `uv run scripts/cnp_prefix_audit.py` pass.
7. No plain-text secrets were introduced.
8. If the app attaches `components/kopiur/backup`: the namespace overlay attaches `kopiur/base`, and a verification snapshot run (`kubectl kopiur snapshot now -n <ns> --policy <app>`) completed with zero `POLICY_DENIED` flows from the mover pod in hubble.

## Notes

- Every app gets its own `ocirepository.yaml` (named after the app), including `app-template` apps. There is no shared/injected `app-template` `OCIRepository`.
- Never put the `OCIRepository` inline in `helmrelease.yaml`; it lives in its own `ocirepository.yaml`.
- Prefer minimal scaffolding that matches existing apps in the same namespace.
- If the workload is not a good fit for `app-template`, stop and ask the user before continuing.
