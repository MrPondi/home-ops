# Dragonfly

Per-app [Dragonfly](https://www.dragonflydb.io/) cache via the `dragonfly-operator` — a reusable Kustomize component in the same style as `components/postgres`. Each app that needs Dragonfly adds this component; it provisions an isolated `Dragonfly` CR in the consumer namespace. No shared cache.

## What it provides

| File                                         | Kind                                    | Description                                                                                                                                                                                                                                                                             |
| -------------------------------------------- | --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`cluster.yaml`](./cluster.yaml)             | `Dragonfly` (`dragonflydb.io/v1alpha1`) | Single-instance Dragonfly `name: ${APP}-dragonfly`, `image: ghcr.io/dragonflydb/dragonfly:v2.0.0`, `replicas: ${DRAGONFLY_REPLICAS:=1}`, `maxmemory` from limits, args `--maxmemory=$(MAX_MEMORY)Mi --proactor_threads=2 --cluster_mode=emulated --version_check=false`.                |
| [`networkpolicy.yaml`](./networkpolicy.yaml) | `CiliumNetworkPolicy`                   | Selects `${APP}-dragonfly` pods (`app`, `app.kubernetes.io/name: dragonfly`, `app.kubernetes.io/part-of: dragonfly`). Ingress: same-namespace consumers via `${DRAGONFLY_APP_NAME:=${APP}}` on `6379/TCP`, operator on `9999/TCP`, prometheus on `9999/TCP`. Egress: DNS to `kube-dns`. |
| [`podmonitor.yaml`](./podmonitor.yaml)       | `PodMonitor`                            | Scrapes Dragonfly metrics on `9999`.                                                                                                                                                                                                                                                    |
| [`authentication/`](./authentication/)       | Component                               | Optional auth sub-component — `Password` generator + `ExternalSecret` (`${APP}-dragonfly-secret`) and JSON6902 patch adding `spec.authentication.passwordFromSecret` to the Dragonfly CR.                                                                                               |

## Substitution variables

Set in the consumer `Kustomization` `postBuild.substitute`:

| Variable             | Required | Default  | Description                                                                                                                                                                                                       |
| -------------------- | -------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `APP`                | **yes**  | —        | App name. Used for Dragonfly resource name `${APP}-dragonfly` and secret `${APP}-dragonfly-secret`.                                                                                                               |
| `DRAGONFLY_APP_NAME` | no       | `${APP}` | Consumer label `app.kubernetes.io/name` allowed to reach Dragonfly on `6379`. Referenced as `${DRAGONFLY_APP_NAME:=${APP}}`. Override when the consumer pod label differs (e.g. `virtualmcpserver` for toolhive). |
| `DRAGONFLY_REPLICAS` | no       | `1`      | Dragonfly replicas. Single-node default `1`.                                                                                                                                                                      |

## Usage

### Consumer Kustomization — without auth

```yaml
# kubernetes/apps/<ns>/<app>/ks.yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
    name: <app>
    labels:
        components.dragonfly/enabled: "true"
spec:
    components: [] # existing entries like ../../../../components/kopiur/backup are fine — root patch appends ../../../../components/dragonfly
    dependsOn:
        - name: external-secrets-store
          namespace: external-secrets
        # + any app-specific deps; root patch appends dragonfly-operator (ns database)
    healthCheckExprs: [] # placeholder — root patch injects Dragonfly readiness check
    interval: 1h
    path: ./kubernetes/apps/<ns>/<app>/app
    postBuild:
        substitute:
            APP: <app>
            # DRAGONFLY_APP_NAME defaults to ${APP} — set only if different (e.g. virtualmcpserver for toolhive-config)
    prune: true
    sourceRef:
        kind: GitRepository
        name: flux-system
        namespace: flux-system
```

### With authentication

```yaml
# kubernetes/apps/<ns>/<app>/ks.yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
    name: <app>
    labels:
        components.dragonfly/enabled: "true"
        components.dragonfly/authentication: "true" # additive — requires enabled as well
spec:
    components: [] # existing entries fine — root patches append dragonfly + authentication
    dependsOn:
        - name: external-secrets-store
          namespace: external-secrets
        # + app-specific deps; root patch appends dragonfly-operator (ns database)
    healthCheckExprs: [] # placeholder — root patch injects Dragonfly readiness check
    postBuild:
        substitute:
            APP: <app>
    prune: true
    sourceRef:
        kind: GitRepository
        name: flux-system
        namespace: flux-system
```

Labeled consumers (`components.dragonfly/enabled=true`) x6: `pelican` (default, +authentication), `nextcloud` (default), `toolhive-config` (ai, +authentication, +cluster-mode non-cluster, `DRAGONFLY_APP_NAME` `virtualmcpserver`), `searxng` (ai), `litellm` (ai), `open-webui` (ai). Only `toolhive-config` sets `DRAGONFLY_APP_NAME`; all others default to `${APP}`.

### Label adoption

Consumers use `components.dragonfly/enabled=true` label with `spec.components: []` instead of the literal `../../../../components/dragonfly` entry; the root `cluster-apps` Kustomization injects the path via a JSON6902 `add` to `/spec/components/-` selected by `components.dragonfly/enabled=true`, and also injects a `dependsOn` entry for `dragonfly-operator` (`database`) and a `healthCheckExprs` entry for `Dragonfly` readiness (`has(status.phase) && status.phase == 'Ready'`). Consumers therefore keep only app-specific `dependsOn` entries and an explicit `healthCheckExprs: []` placeholder (the root JSON6902 `append` needs the list to exist) — `litellm` retains its `ClusterSecretStore` health check alongside the injected Dragonfly check. The optional auth sub-component uses `components.dragonfly/authentication=true` (additive — requires `enabled` as well) to inject `../../../../components/dragonfly/authentication`. Enabled x6: `pelican` (`kubernetes/apps/default/pelican/ks.yaml`, +authentication), `nextcloud` (`kubernetes/apps/default/nextcloud/ks.yaml`), `toolhive-config` (`kubernetes/apps/ai/toolhive/ks.yaml`, +authentication, +cluster-mode non-cluster, `DRAGONFLY_APP_NAME` `virtualmcpserver`), `searxng` (`kubernetes/apps/ai/searxng/ks.yaml`), `litellm` (`kubernetes/apps/ai/litellm/ks.yaml`, keeps its own `ClusterSecretStore` health check alongside the injected Dragonfly check), `open-webui` (`kubernetes/apps/ai/open-webui/ks.yaml`); authentication is additive on `pelican` and `toolhive-config`.

### Cluster-mode override — ToolHive Lua auth storage

Label `components.dragonfly/cluster-mode=non-cluster` triggers the root `cluster-apps` patch (labelSelector `components.dragonfly/cluster-mode=non-cluster` on `kind: Kustomization`) which injects a `spec.patches` JSON6902 patch on the `Dragonfly` CR:

- `remove` `/spec/args/2` — drops `--cluster_mode=emulated` (standalone mode required by ToolHive's Redis Lua scripts; replication remains enabled)
- `add` `/spec/args/-` `value: --default_lua_flags=allow-undeclared-keys` — allows Lua scripts to access undeclared keys

Prerequisite: the `Dragonfly` CR must have `>=3` `spec.args` entries (patch removes index 2). The default component `cluster.yaml` satisfies this. Current consumer is `toolhive-config` (`kubernetes/apps/ai/toolhive/ks.yaml`).

### Dependencies

Consumers declare only `external-secrets-store` (ns `external-secrets`) plus any app-specific dependencies in `spec.dependsOn`; the root `cluster-apps` Kustomization (label `components.dragonfly/enabled=true`) injects `dragonfly-operator` (`database`) via JSON6902.

```yaml
# kubernetes/apps/<ns>/<app>/ks.yaml — what you write
spec:
    dependsOn:
        - name: external-secrets-store
          namespace: external-secrets
        # + app-specific deps if needed
```

Effective rendered `dependsOn` after the root patch:

```yaml
spec:
    dependsOn:
        - name: external-secrets-store
          namespace: external-secrets
        # + app-specific deps
        - name: dragonfly-operator
          namespace: database
```

Order follows `AGENTS.md`: same-namespace deps first, then `external-secrets-store`, then remaining cross-namespace deps — the root patch appends last, preserving this order. `external-secrets-store` stays a manual consumer `dependsOn` (not root-injected) to preserve dependency-chain order since patched entries append last.

### Health check

Consumers keep an explicit `healthCheckExprs: []` placeholder (or existing entries like `litellm`'s `ClusterSecretStore` check); the root `cluster-apps` Kustomization (label `components.dragonfly/enabled=true`) injects the `Dragonfly` readiness check via JSON6902.

```yaml
# kubernetes/apps/<ns>/<app>/ks.yaml — what you write
spec:
    healthCheckExprs: [] # or existing entries e.g. litellm's ClusterSecretStore; root patch appends Dragonfly check
```

Effective rendered entry after the root patch:

```yaml
spec:
    healthCheckExprs:
        - apiVersion: dragonflydb.io/v1alpha1
          kind: Dragonfly
          current: has(status.phase) && status.phase == 'Ready'
          # plus any consumer entries (e.g. litellm's ClusterSecretStore) kept alongside
```

## Connecting

Dragonfly service: `${APP}-dragonfly.<ns>.svc.cluster.local:6379`. With auth, password is in Secret `${APP}-dragonfly-secret` key `password` (templated from `Password` generator `${APP}-dragonfly`).

```yaml
env:
    - name: REDIS_URL
      value: redis://$(REDIS_PASSWORD)@${APP}-dragonfly.<ns>.svc.cluster.local:6379/0
    - name: REDIS_PASSWORD
      valueFrom:
          secretKeyRef:
              name: ${APP}-dragonfly-secret
              key: password
```
