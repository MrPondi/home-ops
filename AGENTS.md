---

# Agent notes for this repository

# Purpose: hard-won operational knowledge for working on this homelab cluster.

# Read this before applying anything to the cluster.

## Git discipline

- **Never run git commands that mutate the repo or index** (`git add`, `git commit`, `git push`, `git stash`, `git restore`, `git checkout`, `git merge`, `git rebase`, `git reset`, `git clean`, ...) unless the user explicitly asks. Staged vs unstaged state is the user's review signal: they use it to see changes between prompts when deciding whether to commit.
- Read-only git (`git status`, `git diff`, `git log`, `git show`) is always fine.

## Cluster facts

- Talos single-node cluster: node `k8s-0` (10.0.30.21, Talos v1.14.x, k8s v1.37.x), kube API also on VIP `k8s.internal` (10.0.30.10:6443; kubeconfig + talosconfig in repo root).
- CNI: Cilium 1.20 (kubeProxyReplacement, native routing, `ipv4NativeRoutingCIDR 10.42.0.0/16`). Hubble + relay exposed locally via `cilium hubble port-forward` (localhost:4245) — check it is running before using hubble.
- GitOps: Flux 2.9.x. Cluster state = `main` branch. Root Kustomization `cluster-apps` (kubernetes/flux/cluster/ks.yaml) walks `kubernetes/apps/` and patches HelmRelease defaults (crds `CreateReplace`, rollback/upgrade remediation) onto every child.
- CIDR map:
    - Pods `10.42.0.0/16`, Services `10.43.0.0/16`
    - Nodes/mgmt `10.0.30.0/24` (envoy-internal VIP `10.0.30.11`, envoy-external `10.0.30.12`, LB IPs also live here)
    - LAN `192.168.1.0/24`, VPN `10.0.199.0/24`
    - QNAP `10.0.25.25` (MinIO S3 on 9000; also fronted as `s3.pondi.dev` → envoy-internal `10.0.30.11:80`)
- Namespaces: repo-managed namespaces mirror `kubernetes/apps/` (network, observability, database, media, ai, default, security, external-secrets, cert-manager, kube-system, flux-system, kopiur-system, miroir-system, longhorn-system, system-upgrade, actions-runner-system). Live extras `cilium-secrets` and `openebs-system` are empty and not Flux-managed — leave them alone.
- Handy `just kube` recipes (kubernetes/mod.just): `sync ks` (force-sync, annotates force-sync/reconcile/forceAt), `apply-ks <ns> <ks>`, `delete-ks <ns> <ks>`, `node-shell <node>`, `browse-pvc <ns> <claim>`, `view-secret <ns> <secret>`, `prune-pods`.

## Repo layout (read before adding anything)

- `kubernetes/apps/<ns>/kustomization.yaml` — namespace overlay. Sets `namespace: <ns>` (this is what namespaces the rendered resources _and_ renames the Namespace placeholder below), lists `./namespace.yaml`, one `./<app>/ks.yaml` per app (alphabetically), and namespace-wide components (`../../components/alerts` is in every overlay).
- `kubernetes/components/replacements/ks.yaml` — kustomize `replacements` list (a bare list, **not** a kustomize component) that stamps `spec.targetNamespace` onto every Kustomization in an overlay render, sourced from the overlay's Namespace object. Each namespace overlay wires it via the top-level `replacements:` field (`- path: ../../components/replacements/ks.yaml`). It must stay top-level: replacements carried by a kustomize component run _before_ the Namespace rename and would read the placeholder name instead. The replacement is the default and the only mechanism — **never** set an explicit `targetNamespace` in an app `ks.yaml` (the replacement stamps it at render time).
- `kubernetes/apps/<ns>/<app>/ks.yaml` — one or more Kustomization docs. Every doc sets `interval: 1h`, `prune: true`, `postBuild.substitute.APP`, and usually `dependsOn: [external-secrets-store]` (namespace `external-secrets`). `spec.targetNamespace` is stamped by the overlay's replacements list — never set it explicitly. Attach shared infra via `spec.components` pointing at `../../../../components/...`.
- Manifests for each Kustomization live in a subdir next to `ks.yaml`: `app/` is the norm; multi-part apps use `backend/`, `client/`, `config/`, `crds/`, `cluster/` (e.g. `pstream`, `toolhive`, `litellm`).
- `kubernetes/apps/<ns>/namespace.yaml` — Namespace placeholder with `name: _` (renamed by the overlay's `namespace:` field), `kustomize.toolkit.fluxcd.io/prune: disabled`. In fail-closed namespaces a `default-deny` NetworkPolicy is folded in here as a second doc.
- Components: `kubernetes/components/` —
    - `alerts`: Flux `Alert`/`Provider` notification objects (flux resource failures → Alertmanager). Injected by every namespace overlay.
    - `generators`: ESO `Password` generator (`hex-32`) for apps needing a generated secret.
    - `kopiur/secret` + `kopiur/backup`: kopia backup secret + backup/snapshot PVC resources, attached per-app.
    - `auth-proxy`: envoy `SecurityPolicy` wiring an app's HTTPRoute through authentik (extAuth); target overridable via `${APP_HTTPROUTE:=${APP}}`.
    - `dragonfly`: per-app Dragonfly CR + CNP + podmonitor; consumer label `${DRAGONFLY_APP_NAME:=${APP}}`.
    - `zeroscaler`: HPA template.
- Components may use `${VAR:=default}` substitution fed by the Kustomization's `postBuild` (see `toolhive`, `auth-proxy` consumers).

## New apps

**Scaffold new apps with the `add-app` skill (`.agents/skills/add-app/SKILL.md`)** — it is the source of truth for file layout, templates, and the verification checklist. Load it before creating anything under `kubernetes/apps/`.

## Flux rules (read before touching the cluster)

- Helm chart sources are per-app: each app declares its own `OCIRepository` in `<subdir>/ocirepository.yaml`, and the HelmRelease's `spec.chartRef.name` matches it. There is no shared/injected app-template repo.
- Kustomize resources in each app dir are listed alphabetically; add new files (e.g. `networkpolicy.yaml`) to the dir's `kustomization.yaml`.
- When live-applying a file manually you **must pass `-n <namespace>`** or it lands in `default`.

### Rollout: git-first, fix forward (default path)

main = cluster state; merge the PR **before** deep verification, not after:

1. Edit manifests → commit → PR → merge to `main`.
2. Force the deploy (root and child KS intervals are 1h — never wait for it): `flux reconcile kustomization <ks> -n <ns> --with-source`, or `just kube sync ks` to force-sync every Kustomization cluster-wide.
3. Verify (hubble for network changes). Broken → follow-up commit or `git revert` → repeat. Fix-forward is cheap, and drift correction now _enforces_ what you tested because git == cluster.

- **Never live-apply flux-managed objects as a routine path** — kustomize-controller silently reverts drift (on sync or interval).

### Rollout: experiment window (apply-ks loop)

When a change needs repeated apply→observe→fix cycles (e.g. CNP selector tuning), open an experiment window instead of fighting drift:

1. `flux suspend kustomization <ks> -n <ns>` — pauses drift correction + deploys for that app only. A child suspend **is sticky** on flux 2.9.5 (SSA-based kustomize-controller v1.9): a forced parent `cluster-apps` reconcile does not clear it (verified 2026-09; the old "only root suspend survives" behavior predates this version).
2. Iterate: edit files → `just kube apply-ks <ns> <ks>` → verify → repeat. `apply-ks` renders locally (flate) and SSA-applies under flux's own `kustomize-controller` field manager, so it converges cleanly once flux resumes.
3. Commit the final change → PR → merge to `main`.
4. `flux resume kustomization <ks> -n <ns>` — un-suspends and immediately reconciles the merged state.

- Cluster-wide freeze (rare, e.g. risky migration): `flux suspend kustomization flux-system -n flux-system`, resume with `flux resume kustomization flux-system -n flux-system`. While suspended NO flux deploys happen anywhere.
- Hygiene: `flux get kustomizations -A` must never show `SUSPENDED True` once the work is done.

### Drift quirks (still true)

- Newly _created_ objects (not yet in git) are invisible to flux prune and persist until the PR merges.
- `kubectl apply` cannot remove fields from flux-managed objects (no last-applied history) — use `kubectl patch --type=merge -p '{...: null}'`.

## Adding new resources

- Every YAML document starts with a `---` separator followed by a schema header pointing at the schema server:
  `# yaml-language-server: $schema=https://k8s-schemas.home-operations.com/<group>/<kind>_v<n>.json`
  (e.g. `cilium.io/ciliumnetworkpolicy_v2.json`, `kustomize.toolkit.fluxcd.io/kustomization_v1.json`). Multi-doc files repeat `---` + header per document. Kustomization files themselves use `https://json.schemastore.org/kustomization`.
- **Sensitive values always go through external-secrets** (`ExternalSecret` → Bitwarden SDK store) — never hardcode secrets, tokens or keys in manifests, chart values or postBuild substitutes. Where templating needs a secret value, wire it via a `substituteFrom` Secret created from an ExternalSecret (see `toolhive` for the pattern).
- **Never guess label selectors or match expressions.** Charts and CRDs pick their own labels and they differ per app. Render first, match second: `just kube render-local-ks <ns> <ks>` (or `kubectl kustomize <dir>` for a not-yet-wired dir) and copy the labels out of the rendered Deployment/CR, then cross-check live pods (`kubectl get pods -o jsonpath='{.items[*].metadata.labels}'`). This applies to anything that must match cluster state: CNPs, ServiceMonitors, PDBs, RBAC, affinity, job selectors.

## CiliumNetworkPolicy conventions

- One file per app dir: `networkpolicy.yaml` (schema header per "Adding new resources").
  Multi-doc files (several CNPs separated by `---`) are an accepted convention for multi-component apps.
- Selectors:
    - `endpointSelector`: plain k8s label keys (`app.kubernetes.io/name: ...`).
    - `fromEndpoints`/`toEndpoints`: `k8s:`-prefixed keys (`k8s:io.kubernetes.pod.namespace: ...`).
    - **Never guess chart labels** — render with flate and copy the real ones (see "Adding new resources"), then cross-check live endpoints (`cilium-dbg endpoint list -o json` → `status.labels["security-relevant"]`).
- Standard building blocks (copy from existing policies):
    - DNS: toEndpoints kube-system + `k8s-app: kube-dns`, ports 53 UDP/TCP, `rules.dns.matchPattern: "*"`
    - Route ingress: fromEndpoints `network` ns + `k8s:app.kubernetes.io/name: envoy` + `k8s:gateway.envoyproxy.io/owning-gateway-name: envoy-internal` (copy from `open-webui`)
    - Metrics ingress: fromEndpoints `observability` ns + `k8s:app.kubernetes.io/name: prometheus`
    - kube API: `toEntities: [host, remote-node]` port 6443
    - Internet: `toCIDRSet 0.0.0.0/0` except `10.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.168.0.0/16`
- Fail-close status (checked 2026-09): **fail-closed namespaces** with a `default-deny` NetworkPolicy folded into `<ns>/namespace.yaml` are `ai`, `database`, `external-secrets`, `cert-manager`, `actions-runner-system`. **Open namespaces** (`default`, `media`, `observability`, `security`, `network`, `kube-system`, ...) have **no** baseline deny.
    - New apps in a fail-closed namespace **must** ship a `networkpolicy.yaml` with ingress + full egress, or the pod is cut off.
    - In an open namespace **do not add a partial CNP**: a CiliumNetworkPolicy isolates its selected pods immediately — an incomplete policy (e.g. DNS-egress-only) breaks the app. Omit it, or write a complete policy (route ingress + full egress).
    - Long-term direction (ROADMAP.md plan 1): app-template chart gains CNP generation; hand-written CNPs are the pattern until then.

## Verifying policies (the loop)

1. Attachment: `kubectl exec -n kube-system ds/cilium -c cilium-agent -- cilium-dbg endpoint list` — every endpoint must show `Enabled` on enforced directions. AWK-parse the table (columns: ENDPOINT, POLICY(ingress), POLICY(egress), IDENTITY, LABELS...) or use `-o json` → `status.policy.realized."policy-enabled"`. The `CiliumEndpoint` CRD does not carry policy status.
2. Live flows: `timeout 60 hubble observe --follow -o json | jq --unbuffered -c '...'`. Zero `POLICY_DENIED` drops in the touched namespaces = good.
3. Event-driven paths (webhooks, backups, cert renewals) do not show up in short captures — trigger them (e.g. CNPG `Backup` CR, ExternalSecret `force-sync` annotation, re-apply a CR) or wait.

## Hubble

- `hubble status` — ring buffer is 4095 flows/node ≈ **6 seconds** at this cluster's flow rate. There is NO history.
- `hubble observe` filters (`--namespace`) apply at the relay buffer, not on nodes — they do NOT give you more history.
- Use `hubble observe --follow` for live capture. `hubble watch` lacks `-o`/`--namespace` flags.
- Flow JSON: `.flow.{verdict, traffic_direction, is_reply, drop_reason_desc, source|destination{namespace, pod_name, labels}, IP, l4.TCP.destination_port, l7.dns.query}`. Filter `.is_reply != true` for original requests; filter `drop_reason_desc | test("POLICY")` for policy drops.
- Flow noise cheat-sheet: `reserved:host` sources are kubelet probes/apiserver/VIP traffic; reply halves double every connection; `UNSUPPORTED_L3_PROTOCOL` drops are ICMP noise, not policy.

## jq / shell pitfalls that cost time here

- Hyphenated keys need quoting: `.pod-name` parses as subtraction → `."pod-name"`.
- `select(A) or B` / `select(A | test(X)) or B` are precedence traps — wrap every condition in parens and use `select(A or B)`.
- hubble json lines include non-flow objects (lost-events markers) — guard with `.flow? // empty` or `select(.flow != null)`.
- Use `--unbuffered` when piping jq into a file mid-stream.
- Background jobs spawned from the tool session are killed when the call ends — run long captures synchronously with `timeout N`.
- The cilium-agent image has **no curl/wget**; for in-cluster HTTP use a throwaway `curlimages/curl` pod (`kubectl run --rm -i ... -- -s http://...`).
- Prometheus API from inside the cluster: `http://prometheus-kube-prometheus-stack.observability:9090/api/v1/query` (URL-encode queries).

## Alerting / monitoring (what exists now)

- Hubble metrics are scraped from `svc/hubble-metrics` (kube-system, port 9965, 10s interval). Drop and flow metrics carry `source_namespace`/`destination_namespace` via `hubble-metrics: ... drop:labelsContext=source_namespace,destination_namespace flow:labelsContext=...` in the cilium helmrelease values (changing it requires a cilium agent restart).
- PrometheusRule `cilium-rules` (kube-system/cilium/app): `CiliumPolicyEgressDrops` (`source_namespace!=""`) and `CiliumPolicyIngressDrops` (`destination_namespace!=""` + `source_namespace=""`) on `increase(hubble_drop_total{reason="POLICY_DENIED"}[10m]) > 0`, severity critical.
- Alertmanager (kube-prometheus-stack app, `alertmanagerconfig.yaml`): severity `critical` → Pushover. groupWait 1m, repeatInterval 12h. `InfoInhibitor` → blackhole, `Watchdog` → buddy-heartbeat. Alerts keep firing ~10-15m after drops stop (10m rate window) then resolve automatically.
- The ingress rule only matches external sources (`source_namespace=""`) so cross-namespace/egress drops don't double-alert.
- `hubble_drop_total` (namespace labels, `reason` label) is preferred over `hubble_flows_processed_total` for drop alerting — the flow metric has no drop-reason label.
