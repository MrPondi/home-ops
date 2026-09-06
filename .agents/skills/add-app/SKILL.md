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
- The namespace overlay wires the `replacements` list (`kubernetes/components/replacements/ks.yaml`, via the overlay's top-level `replacements:` field) which stamps `spec.targetNamespace` onto every Kustomization from the overlay's Namespace object. An explicit `targetNamespace` in `ks.yaml` is redundant but must match the namespace
- Every app declares its own per-app `OCIRepository` in `ocirepository.yaml`; `app-template` apps point `spec.chartRef.name` at that per-app repo (named after the app). There is no shared/injected chart source
- Secrets use `external-secrets` with the `bitwarden-secretsmanager` `ClusterSecretStore`
- Fail-closed namespaces (baseline `default-deny` NetworkPolicy folded into `namespace.yaml`): `ai`, `database`, `external-secrets`, `cert-manager`, `actions-runner-system`. **Apps in these namespaces must ship a `networkpolicy.yaml`**. In open namespaces (`default`, `media`, `observability`, `security`, `network`, ...) do **not** scaffold a CNP unless it is complete (a CNP isolates its pods immediately)
- The root `cluster-apps` Kustomization already patches HelmRelease defaults (crds `CreateReplace`, rollback/upgrade remediation) — do not add them to the app

## Workflow

### Step 1: Collect application details

Use the `question` tool to gather:

1. App name
2. Namespace/category, such as `default`, `media`, or `ai`
3. Image repository
4. Image tag or digest
5. Primary service port
6. Whether the app needs an `ExternalSecret`
7. Whether the app needs persistence
8. Whether the app needs an ingress route (envoy-internal / envoy-external) — if yes, plan for gatus/homepage route annotations
9. Flux `dependsOn` entries for the Kustomization (usually `external-secrets-store` in namespace `external-secrets`)

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

- `networkpolicy.yaml` — **required** in a fail-closed namespace, otherwise omit (or make complete: route ingress + full egress)
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

Add `./networkpolicy.yaml` (fail-closed namespaces), `./externalsecret.yaml`, and other resource files only when required. Keep the resource list alphabetized.

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

#### `kubernetes/apps/<namespace>/<app>/app/networkpolicy.yaml` (fail-closed namespaces only)

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
    ingress: [] # add route ingress when the app is routed: copy the envoy-internal block from a same-namespace app (e.g. open-webui)
    egress:
        # DNS
        - toEndpoints:
              - matchLabels:
                    k8s:io.kubernetes.pod.namespace: kube-system
                    k8s-app: kube-dns
          toPorts:
              - ports:
                    - port: "53"
                      protocol: UDP
                    - port: "53"
                      protocol: TCP
                rules:
                    dns:
                        - matchPattern: "*"
```

An incomplete CNP cuts the pod off. Copy each additional building block (route ingress, kube API, metrics ingress, CIDR/internet) from a neighboring app's `networkpolicy.yaml` in the same namespace rather than retyping it from memory.

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
    targetNamespace: <namespace>
    wait: false
```

Drop `dependsOn` when the app has no secrets or external deps. Add `components` (pointing at `../../../../components/...`) and `healthCheckExprs` only when the app needs them. Follow nearby `ks.yaml` files in the same namespace for exact patterns. The overlay's `replacements` component stamps `spec.targetNamespace` from the Namespace object — the explicit value above must equal `<namespace>` (or be omitted in overlays already wired to the replacement).

### Step 6: Update the namespace overlay

Update:

`kubernetes/apps/<namespace>/kustomization.yaml`

Add:

```yaml
resources:
    - ./<app>/ks.yaml
```

Keep the resource list alphabetized.

### Step 7: Verify

Verify that:

1. `kubernetes/apps/<namespace>/<app>/` contains `ks.yaml` and the `app/` subdir with `helmrelease.yaml`, `kustomization.yaml`, `ocirepository.yaml` (plus `networkpolicy.yaml`/`externalsecret.yaml` when applicable).
2. The overlay kustomization lists `./<app>/ks.yaml` and the app's kustomization lists every created file.
3. `ks.yaml` sets `targetNamespace` and `postBuild.substitute.APP` and its `path` points at the right subdir.
4. The app has its own `ocirepository.yaml` (named after the app), and the HelmRelease's `spec.chartRef.name` matches it.
5. In a fail-closed namespace the CNP covers ingress + full egress; no CNP was added in an open namespace.
6. Render cleanly: `just kube render-local-ks <ns> <app>` (or `kubectl kustomize <dir>` before the overlay entry is added).
7. No plain-text secrets were introduced.

## Notes

- Every app gets its own `ocirepository.yaml` (named after the app), including `app-template` apps. There is no shared/injected `app-template` `OCIRepository`.
- Never put the `OCIRepository` inline in `helmrelease.yaml`; it lives in its own `ocirepository.yaml`.
- Prefer minimal scaffolding that matches existing apps in the same namespace.
- If the workload is not a good fit for `app-template`, stop and ask the user before continuing.
