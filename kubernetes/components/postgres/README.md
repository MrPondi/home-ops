# Postgres

Per-app [CloudNativePG](https://cloudnative-pg.io/) `Cluster` via the **Barman Cloud plugin** (`barman-cloud.cloudnative-pg.io`) — a reusable Kustomize component in the same style as `components/dragonfly`. Each app that needs Postgres adds this component; it provisions an isolated single-node Cluster (with its own `ObjectStore`, `ScheduledBackup`, and S3 credentials) in the consumer namespace. No shared database.

> Adapted from [joryirving/home-ops](https://github.com/joryirving/home-ops) postgres component for this cluster's conventions (Flux, `miroir-slow-local`, QNAP S3).

## Substitution variables

Set in the consumer `Kustomization` `postBuild.substitute` (see [Consumer snippets](#consumer-kustomization-snippets)).

| Variable                | Required | Default  | Description                                                                                                                                                                                                                                                       |
| ----------------------- | -------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `APP`                   | **yes**  | —        | App / Cluster name. Used for `Cluster.metadata.name`, `ObjectStore` name, `ExternalSecret` name (`${APP}-s3`), and backup server name (`serverName`/`barmanObjectName` `${APP}`; `destinationPath` `s3://backups/cloudnative-pg` is shared across all consumers). |
| `POSTGRES_USERNAME`     | no       | `${APP}` | Database and owner created on first `initdb`. Referenced as `${POSTGRES_USERNAME:=${APP}}` so omitting it falls back to `APP`.                                                                                                                                    |
| `POSTGRES_STORAGE_SIZE` | no       | `5Gi`    | PVC size for the Cluster (`spec.storage.size`). Override per app as needed. Storage class is fixed to `miroir-slow-local` (single-node).                                                                                                                          |

All other values are fixed for this homelab: single instance (`instances: 1`, `enablePDB: false`, `podAntiAffinityType: required` is best-effort on one node), image `ghcr.io/cloudnative-pg/postgresql:18.6`, QNAP S3 endpoint `http://qnap.internal:9000`.

## Component files

| File                                             | Kind                                        | Description                                                                                                                                                                                                                                                                                                                                                                               |
| ------------------------------------------------ | ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`cluster.yaml`](./cluster.yaml)                 | `Cluster` (`postgresql.cnpg.io/v1`)         | Single-node CNPG Cluster `name: ${APP}`, `storageClass: miroir-slow-local`, `imageName: ghcr.io/cloudnative-pg/postgresql:18.6@sha256:…`. Plugin `barman-cloud.cloudnative-pg.io` with `barmanObjectName: ${APP}` / `serverName: ${APP}` for both WAL archiving and restore. `annotations: cnpg.io/skipEmptyWalArchiveCheck: "enabled"` lets a fresh recovery Cluster start without WALs. |
| [`objectstore.yaml`](./objectstore.yaml)         | `ObjectStore` (`barmancloud.cnpg.io/v1`)    | Per-app S3 store `name: ${APP}`. `destinationPath: s3://backups/cloudnative-pg` (shared across all consumers), `endpointURL: http://qnap.internal:9000`, `retentionPolicy: 7d`, bzip2 compression, `maxParallel: 4`. Credentials from Secret `${APP}-s3` (`MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY`). Sidecar requests `50m` / limits `300Mi`.                                              |
| [`scheduledbackup.yaml`](./scheduledbackup.yaml) | `ScheduledBackup` (`postgresql.cnpg.io/v1`) | `name: ${APP}-daily`, `schedule: "@daily"`, `immediate: true`, `method: plugin`, `pluginConfiguration.name: barman-cloud.cloudnative-pg.io`. Creates daily base backups and drives WAL archiving via the plugin.                                                                                                                                                                          |
| [`externalsecret.yaml`](./externalsecret.yaml)   | `ExternalSecret` (`external-secrets.io/v1`) | `name: ${APP}-s3` → `ClusterSecretStore/bitwarden-secretsmanager`, `key: cloudnative-pg` (shared Bitwarden item). Syncs `MINIO_ACCESS_KEY` and `MINIO_SECRET_KEY` into Secret `${APP}-s3` in the consumer namespace. One secret per app namespace; no cross-namespace sharing.                                                                                                            |

**No `networkpolicy.yaml` in v1.** Expected consumers live in open namespaces (e.g. `default`, `media`) which have no baseline `default-deny`. If you consume this component from a fail-closed namespace (`ai`, `database`, `external-secrets`, `cert-manager`, `actions-runner-system` — see `AGENTS.md`), you must add a per-app `CiliumNetworkPolicy` for the Cluster's extra routes (S3 egress to `qnap.internal:9000` already via `ObjectStore` sidecar, plus any app egress to `${APP}-rw`). The component itself does not ship one to avoid an incomplete isolation policy in open namespaces.

## Bootstrap behavior

Default bootstrap is **recovery from S3** so rebuilt Clusters restore from the latest backup:

```yaml
# cluster.yaml (default)
metadata:
    annotations:
        cnpg.io/skipEmptyWalArchiveCheck: "enabled" # allows first boot with empty WAL archive
spec:
    bootstrap:
        recovery:
            source: ${APP}-backup
    externalClusters:
        - name: ${APP}-backup
          plugin:
              enabled: true
              isWALArchiver: true
              name: barman-cloud.cloudnative-pg.io
              parameters:
                  barmanObjectName: ${APP}
                  serverName: ${APP} # must match ObjectStore serverName
                  # destinationPath is s3://backups/cloudnative-pg (shared across all consumers), set in ObjectStore
```

- `serverName: ${APP}` — Barman server name; ties `Cluster` ↔ `ObjectStore` ↔ `ScheduledBackup`.
- `s3://backups/cloudnative-pg` — shared prefix on QNAP MinIO (`http://qnap.internal:9000`), retention `7d`; per-app isolation via `serverName`/`barmanObjectName` `${APP}`.
- `skipEmptyWalArchiveCheck: "enabled"` — recovery succeeds even when the WAL archive is still empty (fresh namespace).

### Net-new cluster (empty backup set)

On the very first deploy there is no backup for `serverName` `${APP}` under the shared prefix `s3://backups/cloudnative-pg`, so recovery would fail. Add a **temporary** label to the consumer `Kustomization` to swap bootstrap to `initdb`; remove it after the first backup lands. The root `cluster-apps` Kustomization watches for this label and injects the initdb patch.

```yaml
# kubernetes/apps/<ns>/<app>/ks.yaml — TEMPORARY label, remove after first backup
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
    name: <app>-db
    labels:
        components.postgres/enabled: "true"
        components.postgres/cnpg: init # TEMPORARY net-new bootstrap — remove after first backup lands (just kube pg-initial-backup <ns> <app>); recovery is the default once a backup exists
spec:
    components: [] # existing entries like ../../../../components/kopiur/backup are fine — root patch appends ../../../../components/postgres
    # ... dependsOn, healthCheckExprs, postBuild ...
```

Label `components.postgres/cnpg=init` triggers the root patch (labelSelector `components.postgres/cnpg=init` on `kind: Kustomization`) which injects a strategic-merge doc carrying `spec.patches -> target Cluster (postgresql.cnpg.io/v1)` with JSON6902 ops:

```yaml
- op: replace
  path: /spec/bootstrap
  value: {initdb: {database: ${POSTGRES_USERNAME:=${APP}}, owner: ${POSTGRES_USERNAME:=${APP}}}}
- op: remove
  path: /spec/externalClusters
```

This replaces the default `bootstrap.recovery` (which always exists via the component) with `bootstrap.initdb`, creating database and owner `${POSTGRES_USERNAME:=${APP}}` (defaults to `APP`), and removes `externalClusters`.

> **⚠️ WARNING — MUST remove label after first backup:** This label **MUST** be removed after the first successful base backup (`just kube pg-initial-backup <ns> <app>` + verify `Backup` `Completed`); leaving it means a future full recreate (Cluster CR + PVCs deleted) would bootstrap an **EMPTY** database via `initdb` instead of recovering from Barman.

**Check before removing the label — `kubectl get backup -n <ns>` must show `Completed`:**

```bash
kubectl get backup -n <ns>
# NAME              CLUSTER   PHASE       ...
# pstream-initial   pstream   Completed
```

When `PHASE` is `Completed`, delete the `labels: {components.postgres/cnpg: init}` entry (and the TEMPORARY comment), commit, and Flux will reconcile. Future rebuilds use `recovery` automatically.

Real example: `kubernetes/apps/default/pstream/ks.yaml` (`pstream-backend` Kustomization) carried this label until its first backup landed (since removed — recovery is the default).

### Label precondition (per-consumer)

The `components.postgres/cnpg=init` label itself needs **no** `spec.components` — it is a strategic-merge `spec.patches` injection (like `components.dragonfly/cluster-mode=non-cluster`). Labels that append via JSON6902 `op: add` with `path: /spec/components/-`, `/spec/dependsOn/-` or `/spec/healthCheckExprs/-` _do_ require the labeled `Kustomization` to carry each required field as a list (empty `[]` allowed) — per-consumer scoping (only the adopting KS needs it). Enforced by `scripts/ks_label_precondition_audit.py` and `.github/workflows/validate.yaml` (job `label-preconditions`), registry-driven from `kubernetes/flux/cluster/ks.yaml` (derived from which `labelSelector` entries pair with a JSON6902 `add` to `/spec/components/-`, `/spec/dependsOn/-` or `/spec/healthCheckExprs/-`; 2 strategic-merge selectors need no precondition, 3 components appends + 5 dependsOn appends + 2 healthCheckExprs appends have Rule A active).

### Label adoption

Consumers set label `components.postgres/enabled=true` with `spec.components` as a list (empty `[]` or existing entries like `kopiur/backup` — patch appends), `spec.dependsOn` containing the manual `external-secrets-store` (`external-secrets`) entry (every consumer ships its own `externalsecret.yaml`) plus any app-specific deps, and `spec.healthCheckExprs: []`; the root `cluster-apps` Kustomization injects `../../../../components/postgres` via a JSON6902 `add` to `/spec/components/-` selected by `components.postgres/enabled=true`, and also injects `dependsOn` entries for `external-secrets-store` (`external-secrets`) FIRST, then `barman-cloud` (`database`) and `cloudnative-pg` (`database`), and a `healthCheckExprs` entry for `Cluster` readiness (`status.conditions.filter(e, e.type == 'Ready').all(e, e.status == 'True')` with `failed: status.conditions.filter(e, e.type == 'Ready').all(e, e.status == 'False')`). The manual `external-secrets-store` entry is kept — every labelled consumer ships its own `externalsecret.yaml`, so the rendered list intentionally contains `external-secrets-store` twice (manual + injected); Flux tolerates the duplicate as a redundant Ready check. Consumers keep an explicit `healthCheckExprs: []` placeholder (the root JSON6902 `append` needs the list to exist).

## Usage

### Consumer Kustomization

```yaml
# kubernetes/apps/<ns>/<app>/ks.yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
    name: <app>-db
    labels:
        components.postgres/enabled: "true"
spec:
    components: [] # existing entries like ../../../../components/kopiur/backup are fine — root patch appends ../../../../components/postgres
    dependsOn:
        - name: external-secrets-store
          namespace: external-secrets # app ships own externalsecret.yaml — keep manual entry; root patch adds second copy first (intentional duplicate, Flux tolerates)
        # add app-specific deps here as needed
    healthCheckExprs: [] # placeholder — root patch injects CNPG Cluster readiness check
    interval: 1h
    path: ./kubernetes/apps/<ns>/<app>/db
    postBuild:
        substitute:
            APP: <app> # required
            POSTGRES_STORAGE_SIZE: 5Gi # optional, default 5Gi
            # POSTGRES_USERNAME defaults to ${APP} — set only if different
    prune: true
    sourceRef:
        kind: GitRepository
        name: flux-system
        namespace: flux-system
```

### Just command — trigger an immediate base backup

After the Cluster is `Healthy`, create the first backup (or any on-demand backup):

```bash
just kube pg-initial-backup <ns> <app>
# e.g. just kube pg-initial-backup default pstream
```

This applies a `Backup` CR (`<app>-initial`, `method: plugin`, `pluginConfiguration.name: barman-cloud.cloudnative-pg.io`) in namespace `<ns>`:

```yaml
apiVersion: postgresql.cnpg.io/v1
kind: Backup
metadata:
    name: pstream-initial
spec:
    cluster:
        name: pstream
    method: plugin
    pluginConfiguration:
        name: barman-cloud.cloudnative-pg.io
```

The recipe is `arg order ns app` matching `just kube apply-ks` / `browse-pvc`.

## Backups

- **Schedule:** `ScheduledBackup` `s3://backups/cloudnative-pg` (shared across all consumers) with `schedule: "@daily"` and `immediate: true` — first backup runs shortly after the Cluster becomes ready, then daily at midnight.
- **Method:** `plugin` via `barman-cloud.cloudnative-pg.io` (Barman Cloud plugin). Both base backups and WAL archiving go through the same `ObjectStore`.
- **WAL archiving:** continuous via the plugin sidecar (`isWALArchiver: true`, `maxParallel: 4`, bzip2). Enables PITR within the retention window.
- **Retention:** `7d` (`retentionPolicy: 7d` on the `ObjectStore`; `ScheduledBackup` uses `backupOwnerReference: self` so old Backups are pruned with the Cluster).
- **Backend:** QNAP MinIO at `http://qnap.internal:9000` (`s3://backups/cloudnative-pg`, shared; per-app isolation via `serverName` `${APP}`), credentials from Bitwarden item `cloudnative-pg` via `${APP}-s3`.
- **On-demand:** `just kube pg-initial-backup <ns> <app>` or `kubectl apply` a `Backup` CR as above. Check `kubectl get backup -n <ns>` and `kubectl cnpg status <app> -n <ns>`.

## Connecting

CNPG creates a Secret `<cluster>-app` (here `${APP}-app`) in the Cluster namespace with connection credentials. Keys:

| Key        | Value                                                                 |
| ---------- | --------------------------------------------------------------------- |
| `uri`      | `postgresql://<user>:<password>@<host>:5432/<dbname>?sslmode=require` |
| `jdbc-uri` | JDBC variant                                                          |
| `username` | `${POSTGRES_USERNAME:=${APP}}`                                        |
| `password` | generated, managed by CNPG                                            |
| `host`     | `${APP}-rw.<ns>.svc.cluster.local` (read-write service)               |
| `port`     | `5432`                                                                |
| `dbname`   | `${POSTGRES_USERNAME:=${APP}}`                                        |
| `pgpass`   | libpq pgpass line                                                     |

Consume via `secretKeyRef` (never hardcode):

```yaml
env:
    - name: DATABASE_URL
      valueFrom:
          secretKeyRef:
              name: ${APP}-app # e.g. pstream-app
              key: uri
    # or split fields:
    - name: PGHOST
      valueFrom:
          secretKeyRef:
              name: ${APP}-app
              key: host
```

When possible use {{ .Release.Name }} instead of ${APP}

Services managed by CNPG (in the Cluster namespace):

- `${APP}-rw` — read-write (primary) — use this for app connections.
- `${APP}-ro` / `${APP}-r` — disabled in this component (`disabledDefaultServices: ["r","ro"]`); re-enable in `cluster.yaml` if you need read-only.

````

## Optional Pooler (not shipped by default)

This component does **not** ship a `Pooler` — most single-Cluster consumers don't need one. If you need transaction pooling (e.g. `authentik` at scale), paste this alongside the Cluster — it is **not** included by the component:

```yaml
# kubernetes/apps/<ns>/<app>/pooler.yaml — OPTIONAL, not shipped by default
# Uncomment and adjust for apps that need PgBouncer transaction pooling.
# Apply manually or add to your app's kustomization resources; not part of components/postgres.
---
# yaml-language-server: $schema=https://k8s-schemas.home-operations.com/postgresql.cnpg.io/pooler_v1.json
apiVersion: postgresql.cnpg.io/v1
kind: Pooler
metadata:
    name: ${APP}-pooler
spec:
    cluster:
        name: ${APP}
    instances: 2
    type: rw
    pgbouncer:
        poolMode: transaction
        parameters:
            max_client_conn: "1000"
            default_pool_size: "20"
            reserve_pool_size: "5"
            reserve_pool_timeout: "5"
            max_db_connections: "40"
````

Point apps at `<app>-pooler-rw.<ns>.svc.cluster.local:5432` when using the pooler. Keep `instances: 1` on this single-node cluster unless you have tested HA.

## Consumer Kustomization snippets

### `dependsOn` (label-injected operators)

Consumers declare the manual `external-secrets-store` (`external-secrets`) entry (every consumer ships its own `externalsecret.yaml`) plus any app-specific deps in `spec.dependsOn`; the root `cluster-apps` Kustomization (label `components.postgres/enabled=true`) injects `external-secrets-store` (`external-secrets`) first, then `barman-cloud` and `cloudnative-pg` (both `database`) via JSON6902 (intentional duplicate — Flux tolerates the redundant Ready check):

```yaml
# kubernetes/apps/<ns>/<app>/ks.yaml — what you write
spec:
    dependsOn:
        - name: external-secrets-store
          namespace: external-secrets # app ships own externalsecret.yaml — keep; root patch adds second copy
        # add app-specific deps here as needed
```

Effective rendered `dependsOn` after the root patch (manual + injected):

```yaml
spec:
    dependsOn:
        - name: external-secrets-store
          namespace: external-secrets # manual — app's own externalsecret.yaml
        - name: external-secrets-store
          namespace: external-secrets # injected — root patch (FIRST)
        - name: barman-cloud
          namespace: database # injected
        - name: cloudnative-pg
          namespace: database # injected
```

### `healthCheckExprs` (label-injected)

Consumers keep an explicit `healthCheckExprs: []` placeholder; the root patch injects the CNPG `Cluster` readiness check:

```yaml
# kubernetes/apps/<ns>/<app>/ks.yaml — what you write
spec:
    healthCheckExprs: []
```

Effective rendered entry after the root patch:

```yaml
spec:
    healthCheckExprs:
        - apiVersion: postgresql.cnpg.io/v1
          kind: Cluster
          failed: "status.conditions.filter(e, e.type == 'Ready').all(e, e.status == 'False')"
          current: "status.conditions.filter(e, e.type == 'Ready').all(e, e.status == 'True')"
```

This mirrors the CNPG `Cluster` Ready condition; `healthCheckExprs` (not `healthChecks`) is required for Flux to gate the Kustomization as healthy.

## Verification checklist

After wiring a new consumer (or after changing CNP / ObjectStore):

1. **Render locally** (flate, allow missing secrets):

    ```bash
    just kube render-local-ks <ns> <ks>
    # e.g. just kube render-local-ks default pstream-backend
    ```

    Confirm rendered `Cluster` has `bootstrap.recovery.source: <app>-backup`, `serverName: <app>`, `barmanObjectName: <app>`, `size: <POSTGRES_STORAGE_SIZE>`, and `ObjectStore` `destinationPath: s3://backups/cloudnative-pg` (shared across all consumers).

2. **Hubble drops — zero policy denies:**

    ```bash
    just kube hubble-drops <ns>
    # or bounded capture:
    just kube hubble-capture <ns> 60
    ```

    Expect `0` `POLICY_DENIED` flows from the Cluster pods. If you added a `patches` bootstrap override, this is also when you'd catch a mis-patched Cluster.

3. **CNPG status:**

    ```bash
    kubectl -n <ns> get cluster <app> -o wide
    kubectl -n <ns> cnpg status <app>   # or kubectl cnpg status <app> -n <ns>
    ```

    `phase: Cluster in healthy state`, `instances: 1`, image `ghcr.io/cloudnative-pg/postgresql:18.6`.

4. **Backup CR:**

    ```bash
    just kube pg-initial-backup <ns> <app>
    kubectl -n <ns> get backup -o wide
    kubectl -n <ns> get scheduledbackup <app>-daily -o yaml
    kubectl -n <ns> get objectstore <app> -o yaml
    ```

    `Backup` should reach `Completed`; `ObjectStore` `status` shows last backup; S3 prefix `s3://backups/cloudnative-pg` (shared prefix with per-app `serverName` `${APP}`) contains the backup on QNAP (`http://qnap.internal:9000`).

5. **Secret & service:**

    ```bash
    kubectl -n <ns> get secret <app>-app -o jsonpath='{.data}' | jq
    kubectl -n <ns> get svc <app>-rw -o wide
    ```

6. **Remove temporary label** (if you used net-new `initdb`): delete the `labels: {components.postgres/cnpg: init}` entry (and TEMPORARY comment) from the consumer `ks.yaml`, commit, and re-run `just kube render-local-ks <ns> <ks>` to confirm `bootstrap.recovery` is back before pushing.
