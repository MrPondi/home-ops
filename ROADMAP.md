# Roadmap — Network Policy & Database Components

Planned additions for the cluster, in priority order. Context: after the initial hand-written
Cilium NetworkPolicy rollout (`ai` namespace first, dragonfly component CNP, Hubble behind
authentik), these plans reduce the per-app policy maintenance burden and close the remaining
blast-radius gaps in the shared database layer.

## 1. Chart-generated CiliumNetworkPolicies (custom OCI chart build)

Build a custom OCI image of the [home-operations `app-template` chart](https://github.com/bjw-s-labs/helm-charts)
(`oci://ghcr.io/home-operations/charts`) that generates `CiliumNetworkPolicy` resources from the
same helmrelease values that already generate HTTPRoutes today.

- **Single source of truth**: apps already declare `route:` (hostnames, parentRefs) and `service:`
  blocks in their helmrelease. The chart can derive:
    - `endpointSelector` from controller labels
    - **ingress** from declared routes (envoy-internal / envoy-external parents, app ports)
    - **egress** from a new declarative `networkPolicy:` values block (in-cluster service targets,
      CIDR targets, DNS L7, optional internet allow) — egress intent cannot be safely inferred from
      env vars, so it stays explicit in values
- **Prerequisite for plan 2**: once the chart ships CNPs, every importing app is guaranteed a
  complete egress policy, which is what makes component-carried consumer egress safe
- **Rollout**: chart feature lands first, apps migrate their hand-written CNP to the values block
  one at a time (validation via `flate` render diff + Hubble deny-flow watch, same as the `ai`
  rollout)
- **Fallback**: hand-written per-app CNPs remain the pattern until the chart supports it; nothing
  in the current policies blocks the migration

## 2. Component-carried CNPs (dragonfly pattern) — including consumer egress

Shared components ship their own policies so importers get them for free. Already implemented
for `components/dragonfly` (server-side): `${APP}`-substituted CNP with consumer label defaulting
to `${APP}`, overridable via `${DRAGONFLY_APP_NAME:=${APP}}` (used by toolhive, whose consumers
are `virtualmcpserver` pods).

**Follow-up (deliberately after plan 1)**: move the consumer-side egress rules (DNS + redis
:6379) out of the per-app CNPs and into a second CNP in the component, selecting the consumer
pods via `${DRAGONFLY_APP_NAME:=${APP}}`. Ordering matters:

- **If done before plan 1**, the component egress CNP imposes egress default-deny on every
  consumer pod — an importer without a complete app policy (e.g. nextcloud's commented-out
  dragonfly import) would have its egress clamped to DNS + redis only, breaking communications
- **After plan 1** lands, every importer carries a full chart-generated CNP, so the component
  egress CNP merges additively and the duplicated per-app rules can be deleted

**Candidates**: dragonfly (first), then `components/cnpg` (plan 3), `components/auth-proxy`,
`components/kopiur/backup`. Complements plan 1: components cover shared infrastructure; chart
values cover the app itself.

## 3. CNPG migration: global shared cluster → per-app component

Today every app shares one CNPG cluster (`postgres` in `database`, 1 instance, LoadBalancer `rw`
service, barman backups to MinIO): open-webui, teslamate, authentik, pstream-backend (plus grafana
datasources). One compromised or broken database is a cluster-wide incident, and shared-cluster
egress rules make app CNPs coarse.

**Target**: a `components/postgres` component following the
[joryirving/home-ops postgres component](https://github.com/joryirving/home-ops/blob/main/kubernetes/components/postgres/README.md)
pattern, imported per app:

- `Cluster ${APP}-postgres`: 1 instance on `miroir-slow-local`, `cnpg.io/skipEmptyWalArchiveCheck`
  annotation, default `bootstrap.recovery` from Barman at `s3://postgresql/${APP}/${APP}/` (a torn
  down cluster rebuilds itself from the latest backup + WAL), weekly `ScheduledBackup` + continuous
  WAL archiving, `POSTGRES_USERNAME` defaulting to `${APP}`
- **Net-new DBs** (no prior backup at the destination): add the `components.postgres/cnpg=init`
  label on the consuming Flux Kustomization to switch bootstrap to plain `initdb`; remove the
  label after the first backup exists (bootstrap is only consulted at cluster creation)
- CNPG generates the `${APP}-app` Secret (`uri`, `jdbc-uri`, `host`, `port`, `dbname`, ...) — apps
  connect to the `${APP}-rw` service; no Pooler (add per-cluster later if needed, e.g. authentik
  at scale)
- `healthCheckExprs` on Cluster readiness in each consuming Kustomization
- **CNP included in the component** (ingress from consumer label `${PG_APP_NAME:=${APP}}` +
  prometheus; egress DNS-only) — synergizes with plans 1 and 2

**Migration of existing DBs** (unlike joryirving's net-new flow, data lives on the shared
cluster): per app — import the component with the `cnpg=init` label → `pg_dump` from
`postgres-rw.database` / restore into `${APP}-rw` → create a one-shot `Backup` CR at the new
prefix → remove the `init` label → flip the app's ExternalSecrets to the generated `${APP}-app`
Secret → prune the old database.

**Order** (least disruption first, authentik last — it is the SSO dependency):

1. Create `components/postgres` with backup + metrics + CNP
2. pstream-backend → open-webui → teslamate (dump/restore per app, flip ExternalSecrets, verify,
   drop old DB)
3. authentik (schedule a maintenance window: brief SSO outage during dump/restore)
4. Decommission the shared `postgres` cluster and its LoadBalancer service after the last consumer
   moves; app CNPs then target per-app cluster labels instead of the shared cluster
