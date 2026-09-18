# Dragonfly

Per-app [Dragonfly](https://www.dragonflydb.io/) cache via the `dragonfly-operator` — a reusable Kustomize component in the same style as `components/postgres`. Each app that needs Dragonfly adds this component; it provisions an isolated `Dragonfly` CR in the consumer namespace. No shared cache.

## What it provides

| File                                         | Kind                                    | Description                                                                                                                                                                                                                                                                             |
| -------------------------------------------- | --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`cluster.yaml`](./cluster.yaml)             | `Dragonfly` (`dragonflydb.io/v1alpha1`) | Single-instance Dragonfly `name: ${APP}-dragonfly`, `image: ghcr.io/dragonflydb/dragonfly:v2.0`, `replicas: ${DRAGONFLY_REPLICAS:=1}`, `maxmemory` from limits, args `--maxmemory=$(MAX_MEMORY)Mi --proactor_threads=2 --cluster_mode=emulated`.                                        |
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
spec:
    components:
        - ../../../../components/dragonfly
    dependsOn:
        - name: dragonfly-operator
          namespace: database
        - name: external-secrets-store
          namespace: external-secrets
    postBuild:
        substitute:
            APP: <app>
    # DRAGONFLY_APP_NAME defaults to ${APP} — set only if different
```

### With authentication

```yaml
spec:
    components:
        - ../../../../components/dragonfly
        - ../../../../components/dragonfly/authentication
```

Existing explicit users: `pelican`, `toolhive` (`toolhive-config` also sets `DRAGONFLY_APP_NAME: virtualmcpserver`).

### Cluster-mode override — ToolHive Lua auth storage

Label `components.dragonfly/cluster-mode=non-cluster` triggers the root `cluster-apps` patch (labelSelector `components.dragonfly/cluster-mode=non-cluster` on `kind: Kustomization`) which injects a `spec.patches` JSON6902 patch on the `Dragonfly` CR:

- `remove` `/spec/args/2` — drops `--cluster_mode=emulated` (standalone mode required by ToolHive's Redis Lua scripts; replication remains enabled)
- `add` `/spec/args/-` `value: --default_lua_flags=allow-undeclared-keys` — allows Lua scripts to access undeclared keys

Prerequisite: the `Dragonfly` CR must have `>=3` `spec.args` entries (patch removes index 2). The default component `cluster.yaml` satisfies this. Currently no consumer uses this label — definition only, zero blast radius.

### Dependencies

```yaml
spec:
    dependsOn:
        - name: dragonfly-operator
          namespace: database
        - name: external-secrets-store
          namespace: external-secrets
```

Order follows `AGENTS.md`: same-namespace deps first, then `external-secrets-store`, then remaining cross-namespace deps.

### Health check

```yaml
spec:
    healthCheckExprs:
        - apiVersion: dragonflydb.io/v1alpha1
          kind: Dragonfly
          current: has(status.phase) && status.phase == 'Ready'
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
