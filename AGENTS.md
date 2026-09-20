# Home Operations - AI Assistant Guide

This is a **single-node homelab Kubernetes cluster monorepo** managed with GitOps (Flux, Renovate, GitHub Actions).

## Repository Structure

```
home-ops/
├── .agents/             # AI skills (e.g. add-app scaffolder)
├── .github/             # GitHub Actions workflows (renovate, label-sync, image-pull)
├── .justfile            # Task runner entrypoint (bootstrap / kube / talos modules)
├── kubernetes/          # Kubernetes configurations (Flux-managed)
│   ├── apps/            # Applications grouped by namespace (namespace overlays)
│   ├── components/      # Reusable kustomize components + replacements list
│   └── flux/            # Flux system configuration (root cluster-apps Kustomization)
├── talos/               # Talos Linux machine config templates (minijinja) + mod.just
├── terraform/           # Terraform IaC (proxmox VMs, authentik configuration)
├── scripts/             # Standalone maintenance/audit helper scripts (not cluster-deployed)
└── ROADMAP.md           # Planned work
```

## Cluster Architecture

Single node on a Proxmox hypervisor:

- **k8s-0** (`10.0.30.21`, Talos v1.14.x, Kubernetes v1.37.x) — kube API also on VIP `k8s.internal` (`10.0.30.10:6443`; kubeconfig + talosconfig live in the repo root)
- Workloads and Longhorn block storage coexist on the same node; a separate TrueNAS server handles NFS/SMB shares, media storage, and backups

| Device                                                 | OS               | Purpose                     |
| ------------------------------------------------------ | ---------------- | --------------------------- |
| MS-A2 (Ryzen 9 9955HX, 64GB RAM, Sparkle Arc A310 GPU) | Proxmox          | Hypervisor                  |
| QNAP TS-464 (3×8TB HDD + 1TB M.2)                      | TrueNAS SCALE CE | NFS storage, media, backups |
| UniFi Cloud Gateway Fiber                              | UniFi OS         | Router                      |
| UniFi Network Video Recorder                           | UniFi OS         | NVR (1×6TB HDD)             |
| APC BX1600MI Back-UPS                                  | -                | Backup power                |

CIDR map:

- Pods `10.42.0.0/16`, Services `10.43.0.0/16`
- Nodes/mgmt `10.0.30.0/24` (envoy-internal VIP `10.0.30.11`, envoy-external `10.0.30.12`, LB IPs also live here)
- LAN `192.168.1.0/24`, VPN `10.0.199.0/24`
- QNAP `10.0.25.25` (MinIO S3 on `9000`; also fronted as `s3.pondi.dev` → envoy-internal `10.0.30.11:80`)

Namespaces mirror `kubernetes/apps/` (network, observability, database, media, ai, default, security, external-secrets, cert-manager, kube-system, flux-system, kopiur-system, miroir-system, longhorn-system, system-upgrade, actions-runner-system). Live extras `cilium-secrets` and `openebs-system` are empty and not Flux-managed — leave them alone.

**Fail-closed namespaces** (baseline `default-deny` CiliumNetworkPolicy folded into `<ns>/namespace.yaml`): `ai`, `actions-runner-system`, `cert-manager`, `database`, `external-secrets`, `kopiur-system`, `miroir-system`, `observability`, `security`, `system-upgrade`. The baseline is deny-all ingress + deny-all egress with namespace-wide prometheus metrics ingress allow rule and two egress allow rules: DNS to kube-dns (kube-system) with `rules.dns` L7 inspection and kube-api access on port 6443 — apps in fail-closed namespaces must **not** re-declare a per-app DNS egress rule (it is inherited from `default-deny`). Per-app CNPs only add app-specific egress (services, internet, FQDN). All other namespaces are open (no baseline deny).

## Key Technologies

| Category   | Tool                                   | Purpose                                                                           |
| ---------- | -------------------------------------- | --------------------------------------------------------------------------------- |
| GitOps     | Flux 2.9.x                             | Deploys configs from Git to k8s                                                   |
| CI         | Renovate + GitHub Actions              | Dependency updates, automation                                                    |
| Networking | Cilium 1.20 (eBPF)                     | CNI, kubeProxyReplacement, native routing                                         |
| Visibility | Hubble                                 | Network flow observation (`just kube hubble-*` recipes over a local port-forward) |
| Ingress    | Envoy Gateway                          | L7 proxy (`envoy-internal` / `envoy-external` gateways)                           |
| DNS        | external-dns ×2                        | Private records → UniFi, public records → Cloudflare                              |
| Access     | cloudflared + authentik                | Cloudflare-protected tunnels, SSO/MFA                                             |
| TLS        | cert-manager                           | Certificate automation                                                            |
| Secrets    | external-secrets + Bitwarden SDK store | Secret management                                                                 |
| Storage    | Longhorn                               | Block storage for PVCs                                                            |
| Backups    | kopiur                                 | PVC backup/snapshot orchestration (kopia)                                         |
| Charts     | app-template (bjw-s)                   | Common Helm chart for most apps                                                   |
| Sources    | per-app `OCIRepository`                | Each app declares its own Flux OCI chart source                                   |
| Upgrades   | tuppr                                  | Talos + Kubernetes upgrade automation                                             |
| Validation | flate + yayamlls                       | Local Kustomization/HelmRelease rendering + YAML LSP                              |
| Reviews    | konflate (via ToolHive MCP)            | Rendered-diff evidence for PR reviews                                             |

## GitOps Flow

```
Git push → Flux source sync → Kustomization → HelmRelease → k8s resources
```

Flux recursively walks `kubernetes/apps/` from the root Kustomization `cluster-apps` (`kubernetes/flux/cluster/ks.yaml`), which patches HelmRelease defaults onto every child (crds `CreateReplace`, rollback/upgrade remediation with retries). Cluster state = `main` branch. Each namespace overlay defines a `namespace:` and one Flux `Kustomization` per app (`ks.yaml`).

## Conventions

- **Namespace injection** — `metadata.namespace` is never set inline on `HelmRelease`/`Kustomization` resources. The namespace is injected by the overlay kustomization's `namespace:` field (`kubernetes/apps/<ns>/kustomization.yaml`), which also renames the Namespace placeholder (`kubernetes/apps/<ns>/namespace.yaml`, `name: _`). `spec.targetNamespace` on child Kustomizations is stamped at render time by the replacements list (`kubernetes/components/replacements/ks.yaml`, wired via each overlay's top-level `replacements:` field). The replacement **must** stay top-level: replacements carried by a kustomize component run before the Namespace rename and would read the placeholder name. **Never** set `targetNamespace` explicitly in an app `ks.yaml` — do not flag its absence as a violation.
- **Per-app chart sources** — every app declares its own `OCIRepository` in `<subdir>/ocirepository.yaml`, named after the app; the HelmRelease's `spec.chartRef.name` matches it. There is no shared/injected app-template repo.
- **List ordering rules** — entries in `resources:` lists are grouped into _sections_; each section is sorted within itself (case-insensitive byte order, `./` prefix ignored). Sections appear in this fixed order at the top of the list:
    1. **Files in the kustomization's own directory** — `./<name>.yaml` (e.g. `namespace.yaml`, `helmrelease.yaml`, `externalsecret.yaml`, `networkpolicy.yaml`).
    2. **Files in subdirectories** — `./<subdir>/<name>.yaml` (e.g. mariadb cluster's `databases/`/`grants/`/`users/` per-app groups). Comment-delimited groups (e.g. `# Pelican`) are sub-sections, with the groups themselves sorted.
    3. **Flux Kustomizations** — `./<app>/ks.yaml`. Only occur in namespace overlays, alongside root files (section 1).
    4. **Directory references** — `./<folder>/` (e.g. `./servers/`, `./models/`). Always last in a resource list.
- **Flux Kustomizations (`ks.yaml`)** — top-level keys alphabetized (`apiVersion`, `kind`, `metadata`, `spec`); `spec.*` keys alphabetized (e.g. `healthCheckExprs` sorts before `healthChecks`) except `patches` which are **last**. `spec.dependsOn` is **not** alphabetical — it follows dependency-chain order: same-namespace deps first (operator/crds before the app), then `external-secrets-store` (ns `external-secrets`), then remaining cross-namespace deps. `spec.components` is sorted plain path-alphabetical.
- **Schema headers** — every YAML document starts with a `---` separator followed by a schema header pointing at the schema server: `# yaml-language-server: $schema=https://k8s-schemas.home-operations.com/<group>/<kind>_v<n>.json` (e.g. `cilium.io/ciliumnetworkpolicy_v2.json`, `kustomize.toolkit.fluxcd.io/kustomization_v1.json`). Multi-doc files repeat `---` + header per document. Kustomization files themselves use `https://json.schemastore.org/kustomization`.
- **Formatting** — YAML is 2-space indented (`.editorconfig`); JSON/YAML/Markdown formatting is delegated to the oxc formatter (`.vscode/settings.json`); Git hooks run via lefthook (remote config from `home-operations/.github`).
- **Components** (`kubernetes/components/`):
    - `alerts`: Flux `Alert`/`Provider` objects (resource failures → Alertmanager). Injected by every namespace overlay.
    - `replacements/ks.yaml`: the `spec.targetNamespace` stamping list described above.
    - `generators`: ESO `Password` generator (`hex-32`) for apps needing a generated secret.
    - `kopiur/base`: kopia repository secret + the namespace-wide `kopiur-mover` CNP (mover-job egress), attached by every kopiur-capable namespace overlay.
    - `kopiur/backup`: backup/snapshot PVC resources (SnapshotPolicy + SnapshotSchedule + Restore + PVC), attached per-app.
    - `auth-proxy`: envoy `SecurityPolicy` wiring an app's HTTPRoute through authentik (extAuth); target overridable via `${APP_HTTPROUTE:=${APP}}`.
    - `dragonfly`: per-app Dragonfly CR + CNP + podmonitor; consumer label `${DRAGONFLY_APP_NAME:=${APP}}`.
    - `zeroscaler`: HPA template.
- Components may use `${VAR:=default}` substitution fed by the Kustomization's `postBuild` (see `toolhive`, `auth-proxy`).

## Adding New Apps

Scaffold with the **`add-app` skill** (`.agents/skills/add-app/SKILL.md`) — it is the source of truth for file layout, templates, and the verification checklist. Load it before creating anything under `kubernetes/apps/`. High-level layout:

- `kubernetes/apps/<ns>/kustomization.yaml` — namespace overlay (sets `namespace: <ns>`, lists `./namespace.yaml` + one `./<app>/ks.yaml` per app + namespace-wide components)
- `kubernetes/apps/<ns>/<app>/ks.yaml` — Kustomization doc(s): `interval: 1h`, `prune: true`, `postBuild.substitute.APP`, usually `dependsOn: [external-secrets-store]` (namespace `external-secrets`); shared infra via `spec.components` pointing at `../../../../components/...`
- Manifests for each Kustomization live in a subdir next to `ks.yaml`: `app/` is the norm; multi-part apps use `backend/`, `client/`, `config/`, `crds/`, `cluster/` (e.g. `pstream`, `toolhive`, `litellm`)

## Adding New Resources

- **Sensitive values always go through external-secrets** (`ExternalSecret` → Bitwarden SDK store) — never hardcode secrets, tokens or keys in manifests, chart values or postBuild substitutes. Where templating needs a secret value, wire it via a `substituteFrom` Secret created from an ExternalSecret (see `toolhive` for the pattern).
- **Never guess label selectors or match expressions.** Charts and CRDs pick their own labels and they differ per app. Render first, match second: `just kube render-local-ks <ns> <ks>` (or `kubectl kustomize <dir>` for a not-yet-wired dir) and copy the labels out of the rendered Deployment/CR, then cross-check live pods (`kubectl get pods -o jsonpath='{.items[*].metadata.labels}'`). This applies to anything that must match cluster state: CNPs, ServiceMonitors, PDBs, RBAC, affinity, job selectors.

## Common Operations

The repo is driven by `just` (`just --list`; modules in `.justfile`, `kubernetes/mod.just`, `talos/mod.just`). Common recipes:

- `just kube sync ks` — force-sync every Kustomization (annotates force-sync/reconcile/forceAt)
- `just kube apply-ks <ns> <ks>` / `delete-ks <ns> <ks>` — SSA-apply / delete a locally rendered Kustomization
- `just kube render-local-ks <ns> <ks>` — render kustomization with flate (`--allow-missing-secrets`). **`<ks>` is the Kustomization's `metadata.name`** from the app's `ks.yaml` (e.g. `just kube render-local-ks ai toolhive-config`), not the directory name.
- `just kube node-shell <node>`, `browse-pvc <ns> <claim>`, `view-secret <ns> <secret>`, `prune-pods`
- `just talos apply-node <node>`, `upgrade-k8s <version>`, `upgrade-node <node>`, `render-config <node>`, `reset/reboot/shutdown-node`
- `just template <file>` — minijinja-cli + vals (auto-unlocks Bitwarden via `bw serve` on `:8087`)

When live-applying a file manually you **must pass `-n <namespace>`** or it lands in `default`.

### Validate locally

Run flate before pushing GitOps changes:

```bash
# Render a Kustomization
just kube render-local-ks <ns> <ks>

# Diff against a baseline (e.g. main branch)
git worktree add --detach /tmp/baseline origin/main
just kube render-local-ks <ns> <ks> > /tmp/current.yaml
flate build ks --namespace <ns> --path /tmp/baseline/kubernetes --output yaml --allow-missing-secrets <ks> > /tmp/baseline.yaml
diff -u /tmp/baseline.yaml /tmp/current.yaml
git worktree remove /tmp/baseline --force
```

### Rollout: git-first, fix forward (default path)

main = cluster state; merge the PR **before** deep verification, not after. **Direct pushes to `main` are forbidden** (see **Commit & push hygiene**):

1. Edit manifests → commit → PR → merge to `main`.
2. Force the deploy (root and child KS intervals are 1h — never wait for it): `flux reconcile kustomization <ks> -n <ns> --with-source`, or `just kube sync ks` to force-sync cluster-wide.
3. Verify (hubble for network changes). Broken → follow-up commit or `git revert` → repeat. Fix-forward is cheap, and drift correction now _enforces_ what you tested because git == cluster.

**Never live-apply flux-managed objects as a routine path** — kustomize-controller silently reverts drift (on sync or interval).

### Rollout: experiment window (apply-ks loop)

When a change needs repeated apply→observe→fix cycles (e.g. CNP selector tuning), open an experiment window instead of fighting drift:

1. `flux suspend kustomization <ks> -n <ns>` — pauses drift correction + deploys for that app only. A child suspend **is sticky** on flux 2.9.5 (SSA-based kustomize-controller v1.9): a forced parent `cluster-apps` reconcile does not clear it.
2. Iterate: edit files → `just kube apply-ks <ns> <ks>` → verify → repeat. `apply-ks` renders locally (flate) and SSA-applies under flux's own `kustomize-controller` field manager, so it converges cleanly once flux resumes.
3. Commit the final change → PR → merge to `main`.
4. `flux resume kustomization <ks> -n <ns>` — un-suspends and immediately reconciles the merged state.

- Cluster-wide freeze (rare, e.g. risky migration): `flux suspend kustomization flux-system -n flux-system`; resume with the matching `flux resume`. While suspended NO flux deploys happen anywhere.
- Hygiene: `flux get kustomizations -A` must never show `SUSPENDED True` once the work is done.

### Drift quirks (still true)

- Newly _created_ objects (not yet in git) are invisible to flux prune and persist until the PR merges.
- `kubectl apply` cannot remove fields from flux-managed objects (no last-applied history) — use `kubectl patch --type=merge -p '{...: null}'`.

## Commit & push hygiene

- **Always commit changes when an assignment is complete** — never leave a dirty working tree; partial work belongs in a WIP commit, not in `git status`.
- **Do not push unless the change needs to land.** Push is only load-bearing for changes that drive the rollout pipeline (`kubernetes/`, `talos/`, `terraform/`, CI workflows). Docs-only edits (this file, READMEs) have no cluster effect: committing alone is enough — only push when a PR/main-merge workflow requires it.
- **AI assistants never push directly to `main`.** Rollout changes land via PR only: push a working branch (`agent/<topic>`), `gh pr create`, wait for the required checks, `gh pr merge`, then reconcile. Bypass-privileged credentials are not permission — the account's branch-protection bypass right must never be exercised by automation.
- **`remote: Bypassed rule violations for refs/heads/main:` on a push is a hard stop.** It means branch protection was circumvented: stop immediately, report it to the user, and take no further rollout actions (no retry, no rebase-and-repush, no reconcile) without explicit approval.

## YAML Validation (yayamlls)

`yayamlls` (workspace config `.yayamlls.yaml`, wired in `opencode.json`) is the YAML language server for this repo:

- Kubernetes apiVersion+kind schema auto-detect + schemastore catalog are enabled by default — the `# yaml-language-server: $schema=` headers feed it.
- The **flate renderer** is enabled with `path: kubernetes`: HelmReleases and Kustomizations render inline via code lens + diagnostics by following Flux source references from the cluster root.
- Use its diagnostics (schema validation, rendered-template errors) before/alongside manual `flate` renders; do not disable it in favour of the stock `yaml-ls`.

## Networking & Policy (Cilium)

Cilium 1.20 (kubeProxyReplacement, native routing, `ipv4NativeRoutingCIDR 10.42.0.0/16`). Hubble + relay are reached through a local `cilium hubble port-forward` (localhost:4245) — `just kube hubble-status` ensures the tunnel is up and starts it when needed; the `just kube hubble-flows|drops|capture` recipes build on it (port-forward, reply filtering and jq formatting included).

### CiliumNetworkPolicy conventions

- One file per app dir: `networkpolicy.yaml` (schema header per Conventions). Multi-doc files (several CNPs separated by `---`) are an accepted convention for multi-component apps.
- Selectors (the `k8s:` prefix is **label-source qualification**, not namespace scoping — a CNP bound to a namespace can still cross namespaces by explicitly matching `k8s:io.kubernetes.pod.namespace`, and a prefix changes what object the label is read from):
    - `endpointSelector`: plain k8s label keys (`app.kubernetes.io/name: ...`) — un-prefixed pod labels select within the CNP's own namespace.
    - `fromEndpoints`/`toEndpoints` label meanings:
        - Plain key → `any:` (pod labels + namespace labels union; correct default for same-namespace selects, can't false-negative).
        - `k8s:<key>` → **pod-object** labels only (e.g. `k8s:app.kubernetes.io/name: envoy`); use when the same key may also exist on the namespace object or in mixed selectors.
        - `k8s:io.kubernetes.pod.namespace: <ns>` → canonical cross-namespace selector; matches the namespace **object**, pods do not carry it as a label. Negative targets require an explicitly named namespace or a namespace-label matcher.
        - `io.cilium.k8s.namespace.labels.<key>` → matches pods whose **namespace object** itself carries `<key>`; for grouping across all namespaces at once.
    - **Scope trap**: a CNP selector with only plain/prefixed pod labels — _no_ explicit namespace key — is implicitly clamped to the CNP's own namespace (confirmed via realized-policy selectors, dragonfly-operator 2026-09). "Pods with label X in any namespace" is not expressible in a CNP → use a `CiliumClusterwideNetworkPolicy` with prefixed pod-label selectors (see `dragonfly-operator/app/networkpolicy.yaml`).
    - **Never guess chart labels** — render with flate and copy the real ones, then cross-check live endpoints (`cilium-dbg endpoint list -o json` → `status.labels["security-relevant"]`).
- Every selector endpoint (`fromEndpoints`, `toEndpoints` entries) carries a short comment stating what it matches — e.g. `# Dragonfly operator pods (database/ns-wide)` or `# kube-dns pods (kube-system)`. A selector that compiles but matches nothing is silent; the comment makes the intent reviewable against rendered/live labels.
- Standard building blocks (copy from existing policies):
    - DNS: shipped cluster-wide **per fail-closed namespace** by the `default-deny` CNP in `<ns>/namespace.yaml` (toEndpoints kube-system + `k8s:k8s-app: kube-dns`, ports 53 UDP/TCP, `rules.dns.matchPattern: "*"`); allow rules are additive across policies. Do **not** duplicate it in per-app CNPs in fail-closed namespaces — only in shared components (`kopiur/base`, `dragonfly`) or policies in open namespaces. `toFQDNs` rules in any CNP of a fail-closed ns work thanks to the proxied DNS; FQDN policies without any proxied `:53` DNS won't resolve.
- **Namespace-wide boilerplate in fail-closed namespaces**: the `default-deny` CNP in `<ns>/namespace.yaml` of every fail-closed namespace also ships (1) kube-API egress (`toEntities host/remote-node`, 6443/TCP) and (2) scrape ingress for all pods in the ns from prometheus (observability) on **all ports** (no `toPorts`). Per-app CNPs are therefore **purely additive**: they may omit `ingress:`/`egress:` entirely (the namespace `default-deny` provides the isolation) and must **not** re-declare kube-API egress or prometheus scrape ingress — only ports with different semantics (e.g. litellm :4000) or app-specific routes stay per-app.
- **Shared services in fail-closed namespaces**: stateful services exposing to the whole cluster (databases, message stores, searxng/litellm-class services) declare ingress as a single `fromEntities: [cluster]` rule scoped to their service port (see `database/mariadb/cluster/networkpolicy.yaml`, `cloudnative-pg/cluster`, `ai/litellm/config`, `ai/searxng/app`). **Do not write per-client `fromEndpoints` allow-lists** — a new consumer only edits its own egress CNP. Non-cluster routes (LB/LAN CIDR, operator instance-manager ports, webhooks) and untrusted targets (e.g. toolhive MCP servers) stay explicit per-app.
    - Route ingress: fromEndpoints `network` ns + `k8s:app.kubernetes.io/name: envoy` + `k8s:gateway.envoyproxy.io/owning-gateway-name: envoy-internal` (copy from `open-webui`)
    - Metrics ingress: fromEndpoints `observability` ns + `k8s:app.kubernetes.io/name: prometheus`
    - kube API: `toEntities: [host, remote-node]` port 6443
    - Internet: `toCIDRSet 0.0.0.0/0` except `10.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.168.0.0/16`
    - Kopiur backup egress: shipped namespace-wide by `components/kopiur/base` (mover-only selector) — apps attaching `components/kopiur/backup` need no hand-written rules (see "Kopiur backups" below)
- Fail-closed namespaces (`ai`, `actions-runner-system`, `cert-manager`, `database`, `external-secrets`, `kopiur-system`, `miroir-system`, `observability`, `security`, `system-upgrade`): the namespace `default-deny` provides DNS, kube-API and scrape routes; a per-app `networkpolicy.yaml` is only needed for **app-specific extra routes** (webhooks, S3/internet, cross-ns services, mssql LAN, operator instance-manager ports). An app with no extra routes needs no per-app CNP at all.
- Open namespaces: **do not add a partial CNP** — a CiliumNetworkPolicy isolates its selected pods immediately, and an incomplete policy (e.g. DNS-egress-only) breaks the app. Omit it, or write a complete policy (route ingress + full egress).

### Kopiur backups (snapshot mover jobs)

`components/kopiur/backup` (SnapshotPolicy + SnapshotSchedule + Restore + PVC, attached per-app) backs the app PVC to the `qnap` ClusterRepository (S3 backend → `s3.pondi.dev` on the QNAP MinIO, plain HTTP; credentials from `components/kopiur/base`). The hourly `SnapshotSchedule` (`H * * * *`, Europe/Warsaw) runs this pipeline per app:

1. `VolumeSnapshot` `<snapshot>-snap` (class `longhorn-snapshot-vsc`) of the app PVC — must reach `readyToUse` or the run stalls (`MissingDependency`).
2. Staged source PVC `<snapshot>-src` (longhorn) cloned from the snapshot.
3. A **mover Job** `<snapshot>` in the app namespace runs kopia: image `ghcr.io/home-operations/kopiur-mover` (pin by digest), labels `app.kubernetes.io/managed-by: kopiur` + `kopiur.home-operations.com/config: <app>`, kopia cache on `kopiur-cache-<app>` (`miroir-slow-local`), then applies retention (keepLatest 3, keepHourly 24, keepDaily 7, keepWeekly 4).

**CNP: handled by `components/kopiur/base`** (attached by every kopiur-capable namespace overlay) — it ships the namespace-wide `kopiur-mover` CNP selecting `app.kubernetes.io/managed-by: kopiur`, so apps never hand-write mover rules. Only snapshot/restore mover jobs carry that label; kopiur's own maintenance/discovery/browse jobs deliberately omit it (kopiur source, `consts.rs`), so the CNP is a no-op in namespaces without movers (including `kopiur-system`). Verified request set (2026-09, live runs + hubble):

- DNS → kube-dns :53 UDP/TCP. Denied first = the mover crash-loops (`BackoffLimitExceeded`) before ever touching S3.
- S3 → `s3.pondi.dev:80`. The VIP is `10.0.30.11`, but **Cilium enforces egress on the DNAT-ed backend** — hubble shows `envoy-internal` pods in `network` on port `10080`. The CNP therefore carries a `toEndpoints` rule (network ns + envoy + `envoy-internal` gateway labels, port 10080); a `toCIDR 10.0.30.11/32:80` rule alone **does not work** (verified: mover dial to the VIP times out), it is kept only as a pre-NAT fallback.
- kube API → `host`/`remote-node` :6443 (low volume; progress/status).

**A snapshot run must be performed whenever `components/kopiur/backup` is added or the `kopiur-mover` CNP changes**: `kubectl kopiur snapshot now -n <ns> --policy <app>` triggers a run (inspect with `kubectl kopiur logs -n <ns> snapshot <name>`); hubble must show zero `POLICY_DENIED` flows from the mover pod. Handy `kubectl kopiur` (krew plugin) commands: `status -A`, `doctor`, `snapshots`, `logs`, `maintenance`, `browse`. Restore (populator) movers share the label and the CNP — run the same verification on the first restore in a fail-closed namespace.

### Verifying policies (the loop)

1. Attachment: `kubectl exec -n kube-system ds/cilium -c cilium-agent -- cilium-dbg endpoint list` — every endpoint must show `Enabled` on enforced directions. Use `-o json` → `status.policy.realized."policy-enabled"` (the `CiliumEndpoint` CRD does not carry policy status).
2. Live flows: `just kube hubble-drops <ns>` (interactive follow) or `just kube hubble-capture <ns> 60` (bounded capture; the output file is auto-named under `/tmp` and its path printed). Zero `POLICY_DENIED` drops in the touched namespaces = good.
3. Event-driven paths (webhooks, backups, cert renewals) do not show up in short captures — trigger them (e.g. CNPG `Backup` CR, ExternalSecret `force-sync` annotation, `kubectl kopiur snapshot now -n <ns> --policy <app>`, re-apply a CR) or wait.

### Hubble

- Recipes: `just kube hubble-status` (ensure the port-forward tunnel), `hubble-flows [ns]` (live follow, compact TSV lines: `time, verdict, drop reason, src, dst, :port, dns query`, replies hidden), `hubble-drops [ns]` (POLICY_DENIED only), `hubble-capture [ns] [seconds] [file]` (bounded capture to an auto-named file under `/tmp`, path printed by the recipe; pass `file` to override). `*args` passes through to `hubble observe` (e.g. `just kube hubble-flows ai --pod-name xyz`).
- `hubble status` — ring buffer is 4095 flows/node ≈ **6 seconds** at this cluster's flow rate. There is NO history, and `--namespace` filters apply at the relay buffer (they do NOT give you more history). Use `hubble observe --follow` for live capture (`hubble watch` lacks `-o`/`--namespace` flags).
- Flow JSON: `.flow.{verdict, traffic_direction, is_reply, drop_reason_desc, source|destination{namespace, pod_name, labels}, IP, l4.TCP.destination_port, l7.dns.query}`. Filter `.is_reply != true` for original requests; `drop_reason_desc | test("POLICY")` for policy drops. The cheat-sheet below matters when writing custom jq on top of `hubble-capture` output or raw `hubble observe -o json`.
- Noise cheat-sheet: `reserved:host` sources are kubelet probes/apiserver/VIP traffic; reply halves double every connection; `UNSUPPORTED_L3_PROTOCOL` drops are ICMP noise, not policy.
- **Persistent flow-drop history** (VictoriaLogs): the Hubble dynamic exporter (cilium helmrelease, `hubble.export.dynamic`) writes `DROPPED` verdict flows as JSON lines to `/var/run/cilium/hubble/policy-drops.log` (on-node, exporter-rotated, 10MB×3). The `victoria-logs-collector` vlagent tails it via `-fileCollector.glob` and ships to VictoriaLogs with with `log_source="cilium-hubble"` as a stream field (`fileCollector.streamFields=hostname,log_source`), `_time` taken from the flow's own `time` field (`fileCollector.timeField=time`). Field names match the flow JSON but dotted (`flow.source.namespace`, `flow.source.pod_name`, `flow.l4.TCP.destination_port`, `flow.drop_reason_desc`, `flow.l7.dns.query`), VictoriaLogs auto-parses them from the JSON `_msg`. Query example: `{log_source="cilium-hubble"} | drop_reason_desc:="POLICY_DENIED"` — `_msg` is a placeholder; always filter/select on the structured `flow.*` fields, and use exact filters (`:=`): `POLICY_DENIED` is a single token ( underscores don't split words). Query hubble drops directly in vmui or Grafana Explore (`victorialogs` datasource, plugin `victoriametrics-logs-datasource`). Adjusting exporter filters is hot-reloadable (cilium-flowlog-config ConfigMap) — no agent restart needed.

## Alerting / Monitoring

- Hubble metrics are scraped from `svc/hubble-metrics` (kube-system, port 9965, 10s interval); drop/flow metrics carry `source_namespace`/`destination_namespace` via `labelsContext` in the cilium helmrelease values (changing it requires a cilium agent restart).
- PrometheusRule `cilium-rules` (kube-system): `CiliumPolicyEgressDrops` and `CiliumPolicyIngressDrops` on `increase(hubble_drop_total{reason="POLICY_DENIED"}[10m]) > 0`, severity critical. The ingress rule only matches external sources (`source_namespace=""`) so cross-namespace/egress drops don't double-alert.
- Alertmanager (kube-prometheus-stack `alertmanagerconfig.yaml`): severity `critical` → Pushover (groupWait 1m, repeatInterval 12h). `InfoInhibitor` → blackhole, `Watchdog` → buddy-heartbeat. Alerts keep firing ~10-15m after drops stop (10m rate window) then resolve automatically.
- `hubble_drop_total` is preferred over `hubble_flows_processed_total` for drop alerting — the flow metric has no drop-reason label.
- Prometheus API from inside the cluster: `http://prometheus-kube-prometheus-stack.observability:9090/api/v1/query` (URL-encode queries).

## Shell / jq Pitfalls

- Hyphenated jq keys need quoting: `.pod-name` parses as subtraction → `."pod-name"`.
- `select(A) or B` is a precedence trap — wrap every condition in parens.
- hubble JSON lines include non-flow objects (lost-events markers) — guard with `.flow? // empty`; use `--unbuffered` when piping jq into a file mid-stream.
- Background jobs spawned from a tool session are killed when the call ends — run long captures synchronously with `timeout N`.
- The cilium-agent image has **no curl/wget**; for in-cluster HTTP use a throwaway `curlimages/curl` pod.

## PR Review Standards

When reviewing PRs (including Renovate), enforce these criteria.

### HelmRelease requirements

- Every application is a Flux `HelmRelease` with `spec.chartRef` pointing at the **per-app `OCIRepository`** (named after the app, in its own `ocirepository.yaml`) pinned by `ref.tag`, and a `spec.interval`.
- `install`/`upgrade`/`rollback`/`remediation` defaults are patched globally by the root `cluster-apps` Kustomization — do not add them per-app, and do not flag their absence.
- `metadata.namespace` is **never** set inline on `HelmRelease`/`Kustomization` resources (see Conventions) — reviewers MUST NOT flag its absence.

### Secret management rules

- **NEVER** commit plain-text secrets, tokens or keys in Git — all secrets go through `external-secrets` with the `bitwarden-secretsmanager` `ClusterSecretStore`; templated values via `substituteFrom` Secrets created from ExternalSecrets.
- Talos (`talos/*.yaml.j2` + `vals`/bw-serve) and Terraform (`.sops.yaml` + `age.key`) resolve secrets at render time — this is the intended pattern; do not convert them to external-secrets.

### Image & digest policy

- Container images: prefer `@sha256:` digests over version tags for reproducibility.
- OCI chart artifacts pulled via `OCIRepository` are **exempt**: pin by tag/version.
- Reject updates from untrusted registries; prefer GHCR.io and registry.k8s.io, Docker Hub only as fallback (avoid it for critical infrastructure components).

### Konflate rendered-diff (MCP)

A Konflate MCP server is available through ToolHive. Konflate renders Helm charts and Kustomizations into their final Kubernetes manifests, so its rendered diff shows the actual cluster impact of a PR — not just the raw git changes.

- `get_pr_summary` (pass the PR number): blast radius (added/changed/removed resources), caution lint (data-loss, immutable-field, RBAC, suspend/prune), image changes, render failures. Cheap and high-value — call this first.
- `get_pr_diff` (pass the PR number): the full rendered manifest diff (PR head vs merge-base). Use it when the raw git diff hides the real change — e.g. a HelmRelease version bump or a one-line `values` change that fans out across many resources.
- Surface cautions as caveats or blockers by severity; **treat render failures as blockers** (the manifests may not apply cleanly). Keep digest-only bump reviews compact.

### Breaking change detection

Request changes if:

- API version changes (e.g. `apps/v1beta1` → `apps/v1`), deprecated field usage, or major version bumps without justification
- CRD changes or custom resource modifications
- Network policy or security context relaxations

### Kubernetes ↔ Talos compatibility

Talos pins the node OS and kubelet together; tuppr drives upgrades (`kubernetes/apps/system-upgrade/tuppr/`). When a PR bumps the Kubernetes version (kubelet image, `KubernetesUpgrade` resource, or the `kubernetes` Renovate group), you MUST:

1. Read the deployed Talos version from `talos/` machineconfig templates.
2. Confirm the new Kubernetes version is supported on that Talos release against Talos's published support matrix — search the web for "talos `<version>` kubernetes support matrix" (docs live at `docs.siderolabs.com`).
3. Cite the matrix in the review. Do not approve a Kubernetes bump on "patch release" reasoning without confirming Talos supports it.

## Documentation

- `README.md` — hardware, DNS split, GitOps overview
- `talos/README.md` — Talos machine config notes
- `.agents/skills/add-app/SKILL.md` — app scaffolding workflow
- Component-specific docs live with the component (`kubernetes/apps/**/README.md` when present)

## Python tooling

- Python scripts run through the **uv project at the repo root** (`pyproject.toml` + `uv.lock` + `.python-version`) — never install packages globally (no `pip install --user` / system pip). Add dependencies with `uv add <pkg>` (updates `pyproject.toml` and `uv.lock`, commit both), sync the venv with `uv sync`, and invoke scripts as `uv run scripts/<script>.py`.

## scripts/

Standalone maintenance/audit helpers (not cluster-deployed; see Repository Structure). Invoke via `uv run scripts/<script>.py` — each script documents its usage and configuration in its module docstring and `--help`.

- `cnp_prefix_audit.py` — audits Cilium CNP/CCNP label selectors against the prefix guidelines ("Networking & Policy (Cilium)" → Selectors); exit 1 on violations or unparseable YAML.
- `jellyfin_actor_images.py` — triggers Jellyfin's metadata refresh for persons missing a primary image (needs `JELLYFIN_API_KEY` + `JELLYFIN_USER_ID`). Should be done after a cluster bootstrap due to metadata living on non-restorable pvc.
