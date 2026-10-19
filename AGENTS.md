# Home Operations - AI Assistant Guide

This is a **single-node homelab Kubernetes cluster monorepo** managed with GitOps (Flux, Renovate, GitHub Actions). This file is the source of truth for agents; skills and component READMEs defer to it.

## Repository Structure

```
home-ops/
├── .agents/             # CANONICAL agent config (tool-agnostic) — see "Agent tooling"
│   ├── agents/          # role definitions (coordinator + subagents)
│   ├── adapters/        # per-tool-only settings (opencode lsp, Claude permissions)
│   ├── config.yaml      # default agent, MCP servers, MCP tool denies, protected paths
│   ├── instructions/    # sorting.instructions.md — YAML key-order rules (see Conventions)
│   └── skills/          # AI skills (e.g. add-app scaffolder)
├── .claude/ .mcp.json   # GENERATED Claude Code adapter (agents, skills symlinks, settings, MCP)
├── .github/             # GitHub Actions workflows (renovate, label-sync, image-pull)
├── .mise/               # Env (KUBECONFIG, TALOSCONFIG, FLATE_PATH, .secrets.env) + hooks; tools live in Brewfile
├── .opencode/           # GENERATED opencode adapter (agent/, opencode.json)
├── .justfile            # Task runner entrypoint (bootstrap / kube / talos modules)
├── bootstrap/           # Cluster bootstrap (helmfile + kustomize) + mod.just
├── kubernetes/          # Kubernetes configurations (Flux-managed)
│   ├── apps/            # Applications grouped by namespace (namespace overlays)
│   └── components/      # Reusable kustomize components + replacements list
├── talos/               # Talos Linux machine config templates (minijinja) + mod.just
├── terraform/           # Terraform IaC (proxmox VMs, authentik configuration)
└── scripts/             # Standalone maintenance/audit helper scripts (not cluster-deployed)
```

## Environment

- **Homebrew** (`Brewfile`, `brew bundle`) installs every CLI (flux, kubectl, talosctl, flate, cilium, hubble, helm, uv, …), unpinned. **mise** (`.mise/config.toml`, env + hooks only, no tools) exports `KUBECONFIG`, `TALOSCONFIG`, `FLATE_PATH`, `MINIJINJA_CONFIG_FILE`, `SOPS_AGE_KEY_FILE` and `.secrets.env`. In a shell without mise activation, prefix commands with `mise exec --`. CI installs its own tools via mise-action.
- **Never read, print or commit** `kubeconfig`, `talosconfig`, `age.key`, `.secrets.env` or decrypted SOPS files (all gitignored).
- Scratch files go in a per-session directory (`mktemp -d`), not fixed `/tmp/<name>` paths — parallel sessions clobber each other.

## Agent tooling

This repo is harness-agnostic: `AGENTS.md` (this file; Claude Code reads it natively, `CLAUDE.md` only imports it) and `.agents/` are the single source of truth. Per-tool adapters are **generated** by `scripts/sync_agents.py` — never edit `.claude/`, `.mcp.json`, `.opencode/agent/` or `.opencode/opencode.json` by hand.

- **Change a role / MCP server / skill**: edit `.agents/agents/<role>.md`, `.agents/config.yaml` or `.agents/skills/<name>/`, and commit — the lefthook pre-commit hook regenerates and stages the adapters (`uv run scripts/sync_agents.py` to preview before committing; `--check` exits 1 when they are stale).
- **Role frontmatter** is neutral: `mode` (primary/subagent), `access` (read/write), `bash`, `mcp` (`all`, `none` or a server allow-list), `mcpDeny` (per-server tool globs), `models` (one entry per harness). Prompts stay harness-neutral — no model names, quota numbers or tool-specific tool names in the body.
- **Skills** use the Agent Skills format (`SKILL.md` + frontmatter) under `.agents/skills/`; opencode reads them there, Claude Code via generated `.claude/skills/<name>` symlinks.
- **Adding a harness**: add a `render_<tool>()` to `scripts/sync_agents.py` (returns `{path: content}` + symlinks) and register it in `RENDERERS`; harness-only settings go in `.agents/adapters/`.
- Roles: `homelab-k8s` (default coordinator), `github` (PRs/review), subagents `explorer`, `coder`, `oracle`, `reviewer`, `vision`. Claude Code starts in `homelab-k8s` (`agent` setting); switch with `claude --agent <role>`.

## Cluster Architecture

Single node on a Proxmox hypervisor:

- **k8s-0** (`10.0.30.21`, Talos + Kubernetes, versions per "Versions" below) — kube API also on VIP `k8s.internal` (`10.0.30.10:6443`)
- Workloads and Longhorn block storage coexist on the same node; a separate TrueNAS server handles NFS/SMB shares, media storage, and backups

| Device                                                 | OS               | Purpose                     |
| ------------------------------------------------------ | ---------------- | --------------------------- |
| MS-A2 (Ryzen 9 9955HX, 64GB RAM, Sparkle Arc A310 GPU) | Proxmox          | Hypervisor                  |
| QNAP TS-464 (3×8TB HDD + 1TB M.2)                      | TrueNAS SCALE CE | NFS storage, media, backups |
| UniFi Cloud Gateway Fiber                              | UniFi OS         | Router                      |
| UniFi Network Video Recorder                           | UniFi OS         | NVR (1×6TB HDD)             |
| APC BX1600MI Back-UPS                                  | -                | Backup power                |

### Versions

Never hardcode or quote versions from memory — read them from the Renovate-managed source:

| Component                         | Source of truth                                                                                    |
| --------------------------------- | -------------------------------------------------------------------------------------------------- |
| Talos                             | `kubernetes/apps/system-upgrade/tuppr/upgrades/talosupgrade.yaml` (`spec.talos.version`)           |
| Kubernetes                        | `kubernetes/apps/system-upgrade/tuppr/upgrades/kubernetesupgrade.yaml` (`spec.kubernetes.version`) |
| Cilium                            | `kubernetes/apps/kube-system/cilium/app/ocirepository.yaml` (`ref.tag`)                            |
| Flux                              | `kubernetes/apps/flux-system/flux-operator/` + `flux-instance/` (`ref.tag`)                        |
| Any other chart                   | the app's `ocirepository.yaml` (`ref.tag`)                                                         |
| CLIs (talosctl, flux, kubectl, …) | `brew info <formula>` (unpinned)                                                                   |

tuppr reconciles the cluster to the `TalosUpgrade`/`KubernetesUpgrade` versions; the `talos/*.yaml.j2` templates carry the same pins for (re)bootstrap and must be kept in sync when they are bumped.

CIDR map:

- Pods `10.42.0.0/16`, Services `10.43.0.0/16`
- Nodes/mgmt `10.0.30.0/24` (envoy-internal VIP `10.0.30.11`, envoy-external `10.0.30.12`, LB IPs also live here)
- LAN `192.168.1.0/24`, VPN `10.0.199.0/24`
- QNAP `10.0.25.25` (MinIO S3 on `9000`; also fronted as `s3.pondi.dev` → envoy-internal `10.0.30.11:80`)

Namespaces mirror `kubernetes/apps/` (network, observability, database, media, ai, default, security, external-secrets, cert-manager, kube-system, flux-system, kopiur-system, miroir-system, longhorn-system, system-upgrade, actions-runner-system). Live extras `cilium-secrets` and `openebs-system` are empty and not Flux-managed — leave them alone. An app exists in the cluster only if its `./<app>/ks.yaml` is listed (not commented out) in the namespace overlay.

### Fail-closed namespaces

`ai`, `actions-runner-system`, `cert-manager`, `database`, `default`, `external-secrets`, `kopiur-system`, `media`, `miroir-system`, `observability`, `security`, `system-upgrade`.

Each carries a baseline `default-deny` CiliumNetworkPolicy folded into `<ns>/namespace.yaml`: deny-all ingress + egress, plus three namespace-wide allows:

1. DNS egress to kube-dns (kube-system) :53 UDP/TCP with `rules.dns.matchPattern: "*"` L7 inspection (this is what makes `toFQDNs` work).
2. kube-API egress (`toEntities: [host, remote-node]` :6443).
3. Prometheus (observability) scrape ingress on **all ports**.

Per-app CNPs in these namespaces are **purely additive**: they never re-declare these three rules and are only needed for app-specific routes (route ingress, webhooks, cross-ns services, Postgres/Dragonfly, S3/internet/FQDN, LAN). An app with no extra routes needs no CNP. All other namespaces are **open** (no baseline deny) — see "Networking & Policy" for what that implies.

## Agent workflow (definition of done)

For any change under `kubernetes/`, `talos/`, `terraform/` or CI:

1. **Branch** `agent/<topic>` off `main`.
2. **Edit** following Conventions (incl. the sorting rules file). New apps: load the `add-app` skill first.
3. **Render** every touched Kustomization: `just kube render-local-ks <ns> <ks>`; for non-trivial changes diff against `main` (see "Validate locally").
4. **Audit**: `uv run scripts/kustomization_order_audit.py` and `uv run scripts/cnp_prefix_audit.py` (when CNPs changed) — both exit 1 on violations. Fix violations you introduced; report pre-existing ones instead of silently fixing unrelated files.
5. **Commit** with a Conventional Commit message (`type(scope): summary`, `!` for breaking; e.g. `fix(policy): …`, `feat(media): …`, `docs(agents): …`). lefthook runs oxfmt / `just --fmt` / actionlint on commit and restages fixes.
6. **PR**: `git push -u origin agent/<topic>` → `gh pr create` → konflate `get_pr_summary` (render failures are blockers) → wait for required checks → `gh pr merge`.
7. **Deploy**: `flux reconcile kustomization <ks> -n <ns> --with-source` (intervals are 1h — never wait).
8. **Verify**: workload healthy; network changes show zero `POLICY_DENIED` in hubble; event-driven paths triggered (see "Verifying policies"); `flux get kustomizations -A` shows no `SUSPENDED True`.

Docs-only changes stop after step 5 (commit, no push). Read-only/analysis tasks change nothing.

## Tools

### just

The repo is driven by `just` — run `just --list`, `just --list kube`, `just --list talos` for the full set (modules: `.justfile`, `bootstrap/mod.just`, `kubernetes/mod.just`, `talos/mod.just`). High-value recipes:

- `just kube render-local-ks <ns> <ks>` — render with flate (`--allow-missing-secrets`). **`<ks>` is the Kustomization's `metadata.name`** from `ks.yaml` (e.g. `just kube render-local-ks ai toolhive-config`), not the directory name.
- `just kube apply-ks <ns> <ks>` / `delete-ks <ns> <ks>` — SSA-apply / delete a locally rendered Kustomization (experiment window only).
- `just kube sync ks` — force-sync every Kustomization (annotates force-sync/reconcile/forceAt).
- `just kube hubble-status|hubble-flows|hubble-drops|hubble-capture` — see "Hubble".
- `just kube pg-initial-backup <ns> <app>` — immediate CNPG base backup (required before removing `components.postgres/cnpg=init`).
- `just kube node-shell <node>`, `browse-pvc <ns> <claim>`, `view-secret <ns> <secret>`, `prune-pods`
- `just talos apply-node|render-config|upgrade-node <node>`, `upgrade-k8s <version>`, `reset/reboot/shutdown-node`
- `just template <file>` — minijinja-cli + vals (auto-unlocks Bitwarden via `bw serve` on `:8087`)

When live-applying a file manually you **must pass `-n <namespace>`** or it lands in `default`.

### MCP servers (ToolHive)

Servers are declared once in `.agents/config.yaml`. Tool names are harness-prefixed (`mcp__ToolHive__<tool>` in Claude Code, `ToolHive_<tool>` in opencode). The ToolHive gateway (`kubernetes/apps/ai/toolhive/config/servers/`) exposes:

| Purpose        | Servers                                                |
| -------------- | ------------------------------------------------------ |
| Cluster state  | `flux`, `kubernetes`, `talos`, `longhorn`              |
| Observability  | `prometheus`, `victoria-logs`, `grafana`               |
| PRs / review   | `konflate`, `github`                                   |
| Upstream docs  | `context7` (chart/library docs — prefer over guessing) |
| Infrastructure | `unifi`, `proxmox`, `cloudflare`, `authentik`          |
| Apps           | `hass`, `jellyfin`, `servarr`, `qbittorrent`, `seerr`  |

Prefer MCP read tools for inspection and diagnosis (Flux status, pod logs, PromQL, LogsQL). Cluster **writes** still follow the git-first rollout — MCP tools never replace a PR.

### yayamlls

`yayamlls` (workspace config `.yayamlls.yaml`; wired for opencode via `.agents/adapters/opencode.base.json`, run it as the YAML LSP in any editor/harness that supports one) is the YAML language server: Kubernetes apiVersion+kind schema auto-detect + schemastore catalog (fed by the `$schema` headers), and the flate renderer (`path: kubernetes`) rendering HelmReleases/Kustomizations inline via code lens + diagnostics. Use its diagnostics before/alongside manual renders; do not swap it for the stock `yaml-ls`.

## Conventions

- **Namespace injection** — `metadata.namespace` is never set inline on `HelmRelease`/`Kustomization` resources. The namespace is injected by the overlay kustomization's `namespace:` field (`kubernetes/apps/<ns>/kustomization.yaml`), which also renames the Namespace placeholder (`kubernetes/apps/<ns>/namespace.yaml`, `name: _`). `spec.targetNamespace` on child Kustomizations is stamped at render time by the replacements list (`kubernetes/components/replacements/ks.yaml`, wired via each overlay's top-level `replacements:` field). The replacement **must** stay top-level: replacements carried by a kustomize component run before the Namespace rename and would read the placeholder name. **Never** set `targetNamespace` explicitly in an app `ks.yaml` — do not flag its absence as a violation.
- **Per-app chart sources** — every app declares its own `OCIRepository` in `<subdir>/ocirepository.yaml`, named after the app; the HelmRelease's `spec.chartRef.name` matches it. There is no shared/injected app-template repo.
- **Key ordering** — `.agents/instructions/sorting.instructions.md` is authoritative for YAML key order: alphabetical by default, `apiVersion/kind/metadata/spec` first, ExternalSecret `spec` order (`refreshInterval`, `secretStoreRef`, `target`, `dataFrom`), and app-template HelmRelease ordering (incl. `TZ: Europe/Warsaw` last in every container `env`). Read it before editing manifests.
- **List ordering rules** — entries in `resources:` lists are grouped into _sections_; each section is sorted within itself (case-insensitive byte order, `./` prefix ignored). Sections appear in this fixed order (enforced by `scripts/kustomization_order_audit.py`):
    1. **Files in the kustomization's own directory** — `./<name>.yaml` (e.g. `namespace.yaml`, `helmrelease.yaml`, `externalsecret.yaml`, `networkpolicy.yaml`).
    2. **Files in subdirectories** — `./<subdir>/<name>.yaml` (e.g. mariadb cluster's `databases/`/`grants/`/`users/` per-app groups). Comment-delimited groups (e.g. `# Pelican`) are sub-sections, with the groups themselves sorted.
    3. **Flux Kustomizations** — `./<app>/ks.yaml`. Only occur in namespace overlays, alongside root files (section 1).
    4. **Directory references** — `./<folder>/` (e.g. `./servers/`, `./models/`). Always last in a resource list.
- **Flux Kustomizations (`ks.yaml`)** — top-level keys alphabetized (`apiVersion`, `kind`, `metadata`, `spec`); `spec.*` keys alphabetized (e.g. `healthCheckExprs` sorts before `healthChecks`) except `patches` which are **last**. `spec.dependsOn` is **not** alphabetical — it follows dependency-chain order: same-namespace deps first (operator/crds/`app-postbuild` before the app), then `external-secrets-store` (ns `external-secrets`), then remaining cross-namespace deps. `spec.components` is sorted plain path-alphabetical.
- **Schema headers** — every YAML document starts with a `---` separator followed by a schema header pointing at the schema server: `# yaml-language-server: $schema=https://k8s-schemas.home-operations.com/<group>/<kind>_v<n>.json` (e.g. `cilium.io/ciliumnetworkpolicy_v2.json`, `kustomize.toolkit.fluxcd.io/kustomization_v1.json`). Multi-doc files repeat `---` + header per document. Kustomization files themselves use `https://json.schemastore.org/kustomization`; app-template HelmReleases use the bjw-s chart schema.
- **Formatting** — YAML is 2-space indented (`.editorconfig`); JSON/YAML/Markdown are formatted by oxfmt (`.oxfmtrc.json`, printWidth 100), run by the lefthook pre-commit hooks (remote config from `home-operations/.github`). Code blocks inside Markdown docs may show formatter-chosen indentation — manifests are always 2-space.

### Components (`kubernetes/components/`)

Attached via a Kustomization's `spec.components` (`../../../../components/...`) unless noted:

- `alerts`: Flux `Alert`/`Provider` objects (resource failures → Alertmanager). Injected by every namespace overlay.
- `replacements/ks.yaml`: the `spec.targetNamespace` stamping list described above.
- `generators`: ESO `Password` generator (`hex-32`) for apps needing a generated secret.
- `kopiur/base`: kopia repository secret + the namespace-wide `kopiur-mover` CNP, attached by every kopiur-capable namespace overlay.
- `kopiur/backup`: backup/snapshot PVC resources (SnapshotPolicy + SnapshotSchedule + Restore + PVC), attached per-app.
- `auth-proxy`: envoy `SecurityPolicy` wiring an app's HTTPRoute through authentik (extAuth); target overridable via `${APP_HTTPROUTE:=${APP}}`.
- `postgres` (**label-driven**): per-app CNPG Cluster + ObjectStore + ScheduledBackup + S3 ExternalSecret + CNP + PodMonitor. Docs: `kubernetes/components/postgres/README.md`.
- `dragonfly` (**label-driven**): per-app Dragonfly CR + CNP + podmonitor; consumer label `${DRAGONFLY_APP_NAME:=${APP}}`; `dragonfly/authentication` sub-component.
- `zeroscaler`: HPA template.

Components may use `${VAR:=default}` substitution fed by the Kustomization's `postBuild` (see `toolhive`, `auth-proxy`).

### Label-driven components

The root `flux-system` Kustomization ("Label UX registry" in the FluxInstance `kustomize.patches`, `kubernetes/apps/flux-system/flux-instance/app/helmrelease.yaml`) patches child Kustomizations by `metadata.labels`. **Never** add `components/postgres` or `components/dragonfly` to `spec.components` by hand — set the label:

| Label                                            | Injects                                                                                                                                              |
| ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `components.postgres/enabled: "true"`            | `components/postgres`; dependsOn `external-secrets-store`, `barman-cloud` + `cloudnative-pg` (database); CNPG Cluster healthCheckExpr                |
| `components.postgres/cnpg: init`                 | `spec.patches` swapping bootstrap recovery → `initdb` (**temporary**: net-new DB only, remove after `just kube pg-initial-backup` shows `Completed`) |
| `components.dragonfly/enabled: "true"`           | `components/dragonfly`; dependsOn `dragonfly-operator` (database); Dragonfly Ready healthCheckExpr                                                   |
| `components.dragonfly/authentication: "true"`    | `components/dragonfly/authentication`; dependsOn `external-secrets-store`                                                                            |
| `components.dragonfly/cluster-mode: non-cluster` | `spec.patches` adjusting Dragonfly args (ToolHive Lua scripts)                                                                                       |

Constraints: JSON6902 appends need the labeled KS to already carry `spec.components`, `spec.dependsOn` and `spec.healthCheckExprs` as lists (`[]` allowed) — a missing list fails the render (caught by the required konflate check). `spec.patches`-injecting labels (`cnpg: init`, `cluster-mode`) require the KS to define **no** `spec.patches` of its own. Render with flate to see the injected result.

### Postbuild secrets (`app-postbuild`)

Values that `postBuild` substitution needs from secrets come from a Secret listed in `spec.postBuild.substituteFrom`. The Secret must exist **before** the consumer Kustomization builds, so it can't live in the app's own path:

- **`app-postbuild` (default)** — each namespace that needs it has `kubernetes/apps/<ns>/app-postbuild/` (a Kustomization named `app-postbuild`, `wait: true`) whose `secrets/` dir holds one `ExternalSecret` per consumer producing `<app>-postbuild-secret` (`ai`: hermes, open-webui, toolhive; `media`: `servarr.yaml` → radarr/sonarr/prowlarr). A consumer adds its ExternalSecret there, lists `- name: app-postbuild` first in `dependsOn`, and sets `substituteFrom: [{kind: Secret, name: <app>-postbuild-secret}]`. A new namespace gets its own `app-postbuild` overlay entry.
- **Bootstrap-seeded** — secrets needed before external-secrets is running come from `bootstrap/kustomize/` (e.g. `cloudflare-tunnel-id-secret` for `network/cloudflare-tunnel`).

## Adding New Apps

Scaffold with the **`add-app` skill** (`.agents/skills/add-app/SKILL.md`) — it is the source of truth for file layout, templates, and the verification checklist. Load it before creating anything under `kubernetes/apps/`. High-level layout:

- `kubernetes/apps/<ns>/kustomization.yaml` — namespace overlay (sets `namespace: <ns>`, lists `./namespace.yaml` + one `./<app>/ks.yaml` per app + namespace-wide components)
- `kubernetes/apps/<ns>/<app>/ks.yaml` — Kustomization doc(s): `interval: 1h`, `prune: true`, `postBuild.substitute.APP`, usually `dependsOn: [external-secrets-store]` (namespace `external-secrets`); shared infra via `spec.components` or component labels
- Manifests for each Kustomization live in a subdir next to `ks.yaml`: `app/` is the norm; multi-part apps use `backend/`, `client/`, `config/`, `crds/`, `cluster/` (e.g. `pstream`, `toolhive`, `litellm`)

## Adding New Resources

- **Sensitive values always go through external-secrets** (`ExternalSecret` → Bitwarden SDK store) — never hardcode secrets, tokens or keys in manifests, chart values or postBuild substitutes. Where templating needs a secret value, use a postBuild secret (see above). Before adding an `ExternalSecret`, read 1-2 neighbouring ones and match their structure (`dataFrom.extract.key`, `target.template.data`).
- **Never guess label selectors or match expressions.** Charts and CRDs pick their own labels and they differ per app. Render first, match second: `just kube render-local-ks <ns> <ks>` (or `kubectl kustomize <dir>` for a not-yet-wired dir) and copy the labels out of the rendered Deployment/CR, then cross-check live pods (`kubectl get pods -o jsonpath='{.items[*].metadata.labels}'`). This applies to anything that must match cluster state: CNPs, ServiceMonitors, PDBs, RBAC, affinity, job selectors.

## Rollout

### Validate locally

Run flate before pushing GitOps changes:

```bash
# Render a Kustomization
just kube render-local-ks <ns> <ks>

# Diff against main
tmp=$(mktemp -d)
git worktree add --detach "$tmp/baseline" origin/main
just kube render-local-ks <ns> <ks> > "$tmp/current.yaml"
flate build ks --namespace <ns> --path "$tmp/baseline/kubernetes" --output yaml --allow-missing-secrets <ks> > "$tmp/baseline.yaml"
diff -u "$tmp/baseline.yaml" "$tmp/current.yaml"
git worktree remove "$tmp/baseline" --force
```

### Git-first, fix forward (default path)

main = cluster state; merge the PR **before** deep verification, not after (steps 6–8 of "Agent workflow"). Broken → follow-up commit or `git revert` → repeat. Fix-forward is cheap, and drift correction _enforces_ what you tested because git == cluster.

**Never live-apply flux-managed objects as a routine path** — kustomize-controller silently reverts drift (on sync or interval).

### Experiment window (apply-ks loop)

When a change needs repeated apply→observe→fix cycles (e.g. CNP selector tuning), open an experiment window instead of fighting drift:

1. `flux suspend kustomization <ks> -n <ns>` — pauses drift correction + deploys for that app only. A child suspend **is sticky** with the SSA-based kustomize-controller: a forced parent `flux-system` reconcile does not clear it.
2. Iterate: edit files → `just kube apply-ks <ns> <ks>` → verify → repeat. `apply-ks` renders locally (flate) and SSA-applies under flux's own `kustomize-controller` field manager, so it converges cleanly once flux resumes.
3. Commit the final change → PR → merge to `main`.
4. `flux resume kustomization <ks> -n <ns>` — un-suspends and immediately reconciles the merged state.

- Cluster-wide freeze (rare, e.g. risky migration): `flux suspend kustomization flux-system -n flux-system`; resume with the matching `flux resume`. While suspended NO flux deploys happen anywhere.
- Hygiene: `flux get kustomizations -A` must never show `SUSPENDED True` once the work is done.

### Drift quirks

- Newly _created_ objects (not yet in git) are invisible to flux prune and persist until the PR merges.
- `kubectl apply` cannot remove fields from flux-managed objects (no last-applied history) — use `kubectl patch --type=merge -p '{...: null}'`.

### Commit & push hygiene

- **Always commit changes when an assignment is complete** — never leave a dirty working tree; partial work belongs in a WIP commit, not in `git status`.
- **Do not push unless the change needs to land.** Push is only load-bearing for changes that drive the rollout pipeline (`kubernetes/`, `talos/`, `terraform/`, CI workflows). Docs-only edits (this file, READMEs, skills) have no cluster effect: committing alone is enough — only push when a PR/main-merge workflow requires it.
- **AI assistants never push directly to `main`.** Rollout changes land via PR only: push a working branch (`agent/<topic>`), `gh pr create`, wait for the required checks, `gh pr merge`, then reconcile. Bypass-privileged credentials are not permission — the account's branch-protection bypass right must never be exercised by automation.
- **`remote: Bypassed rule violations for refs/heads/main:` on a push is a hard stop.** It means branch protection was circumvented: stop immediately, report it to the user, and take no further rollout actions (no retry, no rebase-and-repush, no reconcile) without explicit approval.

## Networking & Policy (Cilium)

Cilium (kubeProxyReplacement, native routing, `ipv4NativeRoutingCIDR 10.42.0.0/16`). Namespace isolation model: see "Fail-closed namespaces".

### CiliumNetworkPolicy conventions

- One file per app dir: `networkpolicy.yaml` (schema header per Conventions). Multi-doc files (several CNPs separated by `---`) are accepted for multi-component apps.
- Selectors (the `k8s:` prefix is **label-source qualification**, not namespace scoping — a CNP bound to a namespace can still cross namespaces by explicitly matching `k8s:io.kubernetes.pod.namespace`, and a prefix changes what object the label is read from; enforced by `scripts/cnp_prefix_audit.py`):
    - `endpointSelector`: plain k8s label keys (`app.kubernetes.io/name: ...`) — un-prefixed pod labels select within the CNP's own namespace.
    - `fromEndpoints`/`toEndpoints` label meanings:
        - Plain key → `any:` (pod labels + namespace labels union; correct default for same-namespace selects, can't false-negative).
        - `k8s:<key>` → **pod-object** labels only (e.g. `k8s:app.kubernetes.io/name: envoy`); use when the same key may also exist on the namespace object or in mixed selectors.
        - `k8s:io.kubernetes.pod.namespace: <ns>` → canonical cross-namespace selector; matches the namespace **object**, pods do not carry it as a label. Negative targets require an explicitly named namespace or a namespace-label matcher.
        - `io.cilium.k8s.namespace.labels.<key>` → matches pods whose **namespace object** itself carries `<key>`; for grouping across all namespaces at once.
    - **Scope trap**: a CNP selector with only plain/prefixed pod labels — _no_ explicit namespace key — is implicitly clamped to the CNP's own namespace (confirmed via realized-policy selectors, dragonfly-operator 2026-09). "Pods with label X in any namespace" is not expressible in a CNP → use a `CiliumClusterwideNetworkPolicy` with prefixed pod-label selectors (see `dragonfly-operator/app/networkpolicy.yaml`).
    - **Never guess chart labels** — render with flate and copy the real ones, then cross-check live endpoints (`cilium-dbg endpoint list -o json` → `status.labels["security-relevant"]`).
- Every rule (`fromEndpoints`/`toEndpoints`/`toCIDRSet`/`toFQDNs` entries) carries a short comment stating what it matches — e.g. `# envoy-internal gateway pods (network)`. Comment the rule, not the inner `matchLabels`. A selector that compiles but matches nothing is silent; the comment makes the intent reviewable against rendered/live labels.
- **Fail-closed namespaces**: per-app CNPs are additive only (see "Fail-closed namespaces") — no DNS, kube-API or prometheus-scrape rules; only ports with different semantics (e.g. litellm :4000) or app-specific routes. DNS rules appear only in shared components (`kopiur/base`, `dragonfly`) and in complete policies in open namespaces.
- **Open namespaces**: do **not** add a partial CNP — a CiliumNetworkPolicy isolates its selected pods immediately, and an incomplete policy (e.g. DNS-egress-only) breaks the app. Omit it, or write a complete policy (route ingress + DNS + kube-API + full egress).
- **FQDN egress** (`toFQDNs`): every FQDN rule must declare **both** the bare name and its search-expanded twin — `matchName: <fqdn>` **and** `matchName: <fqdn>.<namespace>.svc.cluster.local`. Pods resolve via ndots:5 search-path expansion, so the DNS query Cilium's FQDN cache records is the **expanded** name; a bare-name-only `matchName` never matches and the dial stays `POLICY_DENIED` — the app looks locked up even though the rule "exists" (verified: tuppr `factory.talos.dev` upgrade lockup, 2026-09). Wildcarded target sets need the `matchPattern` pair too (`**.<fqdn>` + `**.<fqdn>.<ns>.svc.cluster.local`, see `llmkube`). FQDN rules only resolve where a proxied `:53` DNS rule exists (fail-closed `default-deny` provides it). Reference CNPs: `grafana-operator`, `qui`, `tuppr`.
- **Shared services in fail-closed namespaces**: stateful services exposing to the whole cluster (databases, message stores, searxng/litellm-class services) declare ingress as a single `fromEntities: [cluster]` rule scoped to their service port (see `database/mariadb/cluster/networkpolicy.yaml`, `cloudnative-pg/cluster`, `ai/litellm/config`, `ai/searxng/app`). **Do not write per-client `fromEndpoints` allow-lists** — a new consumer only edits its own egress CNP. Non-cluster routes (LB/LAN CIDR, operator instance-manager ports, webhooks) and untrusted targets (e.g. toolhive MCP servers) stay explicit per-app.
- Standard building blocks (copy from existing policies):
    - Route ingress: fromEndpoints `network` ns + `k8s:app.kubernetes.io/name: envoy` + `k8s:gateway.envoyproxy.io/owning-gateway-name: envoy-internal` (copy from `open-webui`)
    - Metrics ingress (open namespaces only): fromEndpoints `observability` ns + `k8s:app.kubernetes.io/name: prometheus`
    - kube API (open namespaces only): `toEntities: [host, remote-node]` port 6443
    - Internet: `toCIDRSet 0.0.0.0/0` except `10.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.168.0.0/16`
    - Kopiur backup egress: shipped namespace-wide by `components/kopiur/base` — apps attaching `components/kopiur/backup` need no hand-written rules (see "Kopiur backups")

### Verifying policies (the loop)

1. Attachment: `kubectl exec -n kube-system ds/cilium -c cilium-agent -- cilium-dbg endpoint list` — every endpoint must show `Enabled` on enforced directions. Use `-o json` → `status.policy.realized."policy-enabled"` (the `CiliumEndpoint` CRD does not carry policy status).
2. Live flows: `just kube hubble-drops <ns>` (interactive follow) or `just kube hubble-capture <ns> 60` (bounded capture; the output file is auto-named under `/tmp` and its path printed). Zero `POLICY_DENIED` drops in the touched namespaces = good. For anything older than a few seconds, query the persistent drop history in VictoriaLogs (see "Hubble").
3. Event-driven paths (webhooks, backups, cert renewals) do not show up in short captures — trigger them (e.g. CNPG `Backup` CR / `just kube pg-initial-backup`, ExternalSecret `force-sync` annotation, `kubectl kopiur snapshot now -n <ns> --policy <app>`, re-apply a CR) or wait.

## PR Review Standards

When reviewing PRs (including Renovate), enforce these criteria.

### HelmRelease requirements

- Every application is a Flux `HelmRelease` with `spec.chartRef` pointing at the **per-app `OCIRepository`** (named after the app, in its own `ocirepository.yaml`) pinned by `ref.tag`, and a `spec.interval`.
- `install`/`upgrade`/`rollback`/`remediation` defaults are patched globally by the root `flux-system` Kustomization — do not add them per-app, and do not flag their absence.
- `metadata.namespace` is **never** set inline on `HelmRelease`/`Kustomization` resources (see Conventions) — reviewers MUST NOT flag its absence.
- Postgres/Dragonfly components arrive via labels (see "Label-driven components") — do not flag their absence from `spec.components`.

### Secret management rules

- **NEVER** commit plain-text secrets, tokens or keys in Git — all secrets go through `external-secrets` with the `bitwarden-secretsmanager` `ClusterSecretStore`; templated values via `substituteFrom` Secrets created from ExternalSecrets.
- Talos (`talos/*.yaml.j2` + `vals`/bw-serve) and Terraform (`.sops.yaml` + `age.key`) resolve secrets at render time — this is the intended pattern; do not convert them to external-secrets.

### Image & digest policy

- Container images: prefer `@sha256:` digests over version tags for reproducibility.
- OCI chart artifacts pulled via `OCIRepository` are **exempt**: pin by tag/version.
- Reject updates from untrusted registries; prefer GHCR.io and registry.k8s.io, Docker Hub only as fallback (avoid it for critical infrastructure components).

### Konflate rendered-diff (MCP)

Konflate renders Helm charts and Kustomizations into their final Kubernetes manifests, so its rendered diff shows the actual cluster impact of a PR — not just the raw git changes. It also runs as a required PR check.

- `get_pr_summary` (pass the PR number): blast radius (added/changed/removed resources), caution lint (data-loss, immutable-field, RBAC, suspend/prune), image changes, render failures. Cheap and high-value — call this first.
- `get_pr_diff` (pass the PR number): the full rendered manifest diff (PR head vs merge-base). Use it when the raw git diff hides the real change — e.g. a HelmRelease version bump or a one-line `values` change that fans out across many resources.
- Surface cautions as caveats or blockers by severity; **treat render failures as blockers** (the manifests may not apply cleanly). Keep digest-only bump reviews compact.

### Breaking change detection

Request changes if:

- API version changes (e.g. `apps/v1beta1` → `apps/v1`), deprecated field usage, or major version bumps without justification
- CRD changes or custom resource modifications
- Network policy or security context relaxations

For major chart/app bumps, read the upstream release notes (context7 / GitHub releases) and cite the relevant breaking changes.

### Kubernetes ↔ Talos compatibility

Talos pins the node OS and kubelet together; tuppr drives upgrades (`kubernetes/apps/system-upgrade/tuppr/`). When a PR bumps the Kubernetes version (kubelet image, `KubernetesUpgrade` resource, or the `kubernetes` Renovate group), you MUST:

1. Read the deployed Talos version from `kubernetes/apps/system-upgrade/tuppr/upgrades/talosupgrade.yaml` (see "Versions").
2. Confirm the new Kubernetes version is supported on that Talos release against Talos's published support matrix — search the web for "talos `<version>` kubernetes support matrix" (docs live at `docs.siderolabs.com`).
3. Cite the matrix in the review. Do not approve a Kubernetes bump on "patch release" reasoning without confirming Talos supports it.

## Python tooling & scripts

- Python scripts run through the **uv project at the repo root** (`pyproject.toml` + `uv.lock` + `.python-version`) — never install packages globally (no `pip install --user` / system pip). Add dependencies with `uv add <pkg>` (updates `pyproject.toml` and `uv.lock`, commit both), sync with `uv sync`, invoke as `uv run scripts/<script>.py`. Each script documents itself in its docstring and `--help`; audits default to `--path kubernetes` and exit 1 on violations.
- `kustomization_order_audit.py` — `resources:` section ordering, `ks.yaml` key order, `dependsOn` chain order, `components` order (see Conventions).
- `cnp_prefix_audit.py` — CNP/CCNP label-selector prefixes against the Selectors rules; also fails on unparseable YAML.
- `sync_agents.py` — renders per-harness agent adapters from `.agents/` (see "Agent tooling"); `--check` for drift.
- `jellyfin_actor_images.py` — triggers Jellyfin's metadata refresh for persons missing a primary image (needs `JELLYFIN_API_KEY` + `JELLYFIN_USER_ID`). Run after a cluster bootstrap (metadata lives on a non-restorable PVC).

## Documentation

- `README.md` — hardware, DNS split, GitOps overview
- `talos/README.md` — Talos machine config notes
- `.agents/skills/add-app/SKILL.md` — app scaffolding workflow
- `.agents/instructions/sorting.instructions.md` — YAML key-order rules
- `.agents/config.yaml` + `.agents/agents/` — agent roles, MCP servers (see "Agent tooling")
- Component-specific docs live with the component (`kubernetes/components/*/README.md`, `kubernetes/apps/**/README.md` when present)

---

# Reference

Detail that is only needed for the specific task at hand.

## Key Technologies

| Category   | Tool                                    | Purpose                                                                           |
| ---------- | --------------------------------------- | --------------------------------------------------------------------------------- |
| GitOps     | Flux (flux-operator)                    | Deploys configs from Git to k8s                                                   |
| CI         | Renovate + GitHub Actions               | Dependency updates, automation                                                    |
| Networking | Cilium (eBPF)                           | CNI, kubeProxyReplacement, native routing                                         |
| Visibility | Hubble                                  | Network flow observation (`just kube hubble-*` recipes over a local port-forward) |
| Ingress    | Envoy Gateway                           | L7 proxy (`envoy-internal` / `envoy-external` gateways)                           |
| DNS        | external-dns ×2                         | Private records → UniFi, public records → Cloudflare                              |
| Access     | cloudflared + authentik                 | Cloudflare-protected tunnels, SSO/MFA                                             |
| TLS        | cert-manager                            | Certificate automation                                                            |
| Secrets    | external-secrets + Bitwarden SDK store  | Secret management                                                                 |
| Storage    | Longhorn                                | Block storage for PVCs                                                            |
| Databases  | CloudNativePG + barman-cloud, Dragonfly | Per-app Postgres / Redis-compatible stores (label-driven components)              |
| Backups    | kopiur                                  | PVC backup/snapshot orchestration (kopia)                                         |
| Charts     | app-template (bjw-s)                    | Common Helm chart for most apps                                                   |
| Sources    | per-app `OCIRepository`                 | Each app declares its own Flux OCI chart source                                   |
| Upgrades   | tuppr                                   | Talos + Kubernetes upgrade automation                                             |
| Validation | flate + yayamlls                        | Local Kustomization/HelmRelease rendering + YAML LSP                              |
| Reviews    | konflate (via ToolHive MCP)             | Rendered-diff evidence for PR reviews                                             |

GitOps flow: `Git push → Flux source sync → Kustomization → HelmRelease → k8s resources`. Flux recursively walks `kubernetes/apps/` from the root Kustomization `flux-system` (`kubernetes/apps/flux-system/flux-instance/app/helmrelease.yaml` (FluxInstance `kustomize.patches`)), which patches HelmRelease defaults onto every child (crds `CreateReplace`, rollback/upgrade remediation with retries) and applies the label-driven components. Each namespace overlay defines a `namespace:` and one Flux `Kustomization` per app (`ks.yaml`).

## Kopiur backups (snapshot mover jobs)

`components/kopiur/backup` (SnapshotPolicy + SnapshotSchedule + Restore + PVC, attached per-app) backs the app PVC to the `qnap` ClusterRepository (S3 backend → `s3.pondi.dev` on the QNAP MinIO, plain HTTP; credentials from `components/kopiur/base`). The hourly `SnapshotSchedule` (`H * * * *`, Europe/Warsaw) runs this pipeline per app:

1. `VolumeSnapshot` `<snapshot>-snap` (class `longhorn-snapshot-vsc`) of the app PVC — must reach `readyToUse` or the run stalls (`MissingDependency`).
2. Staged source PVC `<snapshot>-src` (longhorn) cloned from the snapshot.
3. A **mover Job** `<snapshot>` in the app namespace runs kopia: image `ghcr.io/home-operations/kopiur-mover` (pin by digest), labels `app.kubernetes.io/managed-by: kopiur` + `kopiur.home-operations.com/config: <app>`, kopia cache on `kopiur-cache-<app>` (`miroir-slow-local`), then applies retention (keepLatest 3, keepHourly 24, keepDaily 7, keepWeekly 4).

**CNP: handled by `components/kopiur/base`** — it ships the namespace-wide `kopiur-mover` CNP selecting `app.kubernetes.io/managed-by: kopiur`, so apps never hand-write mover rules. Only snapshot/restore mover jobs carry that label; kopiur's own maintenance/discovery/browse jobs deliberately omit it (kopiur source, `consts.rs`), so the CNP is a no-op in namespaces without movers (including `kopiur-system`). Verified request set (2026-09, live runs + hubble):

- DNS → kube-dns :53 UDP/TCP. Denied first = the mover crash-loops (`BackoffLimitExceeded`) before ever touching S3.
- S3 → `s3.pondi.dev:80`. The VIP is `10.0.30.11`, but **Cilium enforces egress on the DNAT-ed backend** — hubble shows `envoy-internal` pods in `network` on port `10080`. The CNP therefore carries a `toEndpoints` rule (network ns + envoy + `envoy-internal` gateway labels, port 10080).
- kube API → `host`/`remote-node` :6443 (low volume; progress/status).

**A snapshot run must be performed whenever `components/kopiur/backup` is added or the `kopiur-mover` CNP changes**: `kubectl kopiur snapshot now -n <ns> --policy <app>` triggers a run (inspect with `kubectl kopiur logs -n <ns> snapshot <name>`); hubble must show zero `POLICY_DENIED` flows from the mover pod. Handy `kubectl kopiur` (krew plugin) commands: `status -A`, `doctor`, `snapshots`, `logs`, `maintenance`, `browse`. Restore (populator) movers share the label and the CNP — run the same verification on the first restore in a fail-closed namespace.

## Hubble

- Recipes: `just kube hubble-status` (ensure the `cilium hubble port-forward` tunnel on localhost:4245), `hubble-flows [ns]` (live follow, compact TSV lines: `time, verdict, drop reason, src, dst, :port, dns query`, replies hidden), `hubble-drops [ns]` (POLICY_DENIED only), `hubble-capture [ns] [seconds] [file]` (bounded capture to an auto-named file under `/tmp`, path printed; pass `file` to override). `*args` passes through to `hubble observe` (e.g. `just kube hubble-flows ai --pod-name xyz`).
- `hubble status` — ring buffer is 4095 flows/node ≈ **6 seconds** at this cluster's flow rate. There is NO history, and `--namespace` filters apply at the relay buffer (they do NOT give you more history). Use `hubble observe --follow` for live capture (`hubble watch` lacks `-o`/`--namespace` flags).
- Flow JSON: `.flow.{verdict, traffic_direction, is_reply, drop_reason_desc, source|destination{namespace, pod_name, labels}, IP, l4.TCP.destination_port, l7.dns.query}`. Filter `.is_reply != true` for original requests; `drop_reason_desc | test("POLICY")` for policy drops.
- Noise cheat-sheet: `reserved:host` sources are kubelet probes/apiserver/VIP traffic; reply halves double every connection; `UNSUPPORTED_L3_PROTOCOL` drops are ICMP noise, not policy.
- **Persistent flow-drop history** (VictoriaLogs): the Hubble dynamic exporter (cilium helmrelease, `hubble.export.dynamic`) writes `DROPPED` verdict flows as JSON lines to `/var/run/cilium/hubble/policy-drops.log` (on-node, exporter-rotated, 10MB×3). The `victoria-logs-collector` vlagent tails it via `-fileCollector.glob` and ships it to VictoriaLogs with `log_source="cilium-hubble"` as a stream field (`fileCollector.streamFields=hostname,log_source`), `_time` taken from the flow's own `time` field (`fileCollector.timeField=time`). Field names match the flow JSON but dotted (`flow.source.namespace`, `flow.source.pod_name`, `flow.l4.TCP.destination_port`, `flow.drop_reason_desc`, `flow.l7.dns.query`), auto-parsed from the JSON `_msg`. Query example: `{log_source="cilium-hubble"} | flow.drop_reason_desc:="POLICY_DENIED"` — `_msg` is a placeholder; always filter/select on the structured `flow.*` fields with their full dotted prefix (bare names like `drop_reason_desc` match nothing), and use exact filters (`:=`): `POLICY_DENIED` is a single token (underscores don't split words). Query via the `victoria-logs` MCP server, vmui, or Grafana Explore (`victorialogs` datasource, plugin `victoriametrics-logs-datasource`). Exporter filters are hot-reloadable (cilium-flowlog-config ConfigMap) — no agent restart needed.

## Alerting / Monitoring

- Hubble metrics are scraped from `svc/hubble-metrics` (kube-system, port 9965, 10s interval); drop/flow metrics carry `source_namespace`/`destination_namespace` via `labelsContext` in the cilium helmrelease values (changing it requires a cilium agent restart).
- PrometheusRule `cilium-rules` (kube-system): `CiliumPolicyEgressDrops` and `CiliumPolicyIngressDrops` on `increase(hubble_drop_total{reason="POLICY_DENIED"}[10m]) > 0`, severity critical. The ingress rule only matches external sources (`source_namespace=""`) so cross-namespace/egress drops don't double-alert.
- Alertmanager (kube-prometheus-stack `alertmanagerconfig.yaml`): severity `critical` → Pushover (groupWait 1m, repeatInterval 12h). `InfoInhibitor` → blackhole, `Watchdog` → buddy-heartbeat. Alerts keep firing ~10-15m after drops stop (10m rate window) then resolve automatically.
- `hubble_drop_total` is preferred over `hubble_flows_processed_total` for drop alerting — the flow metric has no drop-reason label.
- Prometheus API: the `prometheus` MCP server, or from inside the cluster `http://prometheus-kube-prometheus-stack.observability:9090/api/v1/query` (URL-encode queries).

## Shell / jq Pitfalls

- Hyphenated jq keys need quoting: `.pod-name` parses as subtraction → `."pod-name"`.
- `select(A) or B` is a precedence trap — wrap every condition in parens.
- hubble JSON lines include non-flow objects (lost-events markers) — guard with `.flow? // empty`; use `--unbuffered` when piping jq into a file mid-stream.
- Background jobs spawned from a tool session are killed when the call ends — run long captures synchronously with `timeout N`.
- The cilium-agent image has **no curl/wget**; for in-cluster HTTP use a throwaway `curlimages/curl` pod.
