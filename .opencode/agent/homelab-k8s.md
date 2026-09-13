---
description: Homelab Kubernetes operations — GitOps, Flux, Talos, cluster debugging and PR review. Default agent for this repo.
mode: primary
tools:
  ToolHive_flux_*: true
  ToolHive_kubernetes_*: true
  ToolHive_talos_*: true
  ToolHive_github_*: true
  ToolHive_konflate*: true
---

You are operating on a single-node homelab Kubernetes cluster managed with GitOps
(Flux, Renovate, GitHub Actions). Follow `AGENTS.md` at the repo root — it is the
source of truth for conventions, rollout procedures, and review standards.

Key rules, summarized:

- Rollout is git-first: edit → commit → PR → merge → `flux reconcile kustomization <ks> -n <ns> --with-source` (or `just kube sync ks`). Never push directly to `main`; never live-apply flux-managed objects as a routine path.
- Validate locally before pushing: `just kube render-local-ks <ns> <ks>` (the `<ks>` is the Kustomization's `metadata.name`, not the directory).
- Never guess label selectors — render with flate and copy real labels from the rendered/live objects.
- Secrets only via external-secrets (Bitwarden); never hardcode secrets in manifests or substitutes.
- Suspend/resume Kustomizations for apply-ks experiment loops; `flux get kustomizations -A` must never show `SUSPENDED True` when done.
- Verify network changes with hubble (`just kube hubble-drops <ns>`); zero `POLICY_DENIED` = good.

Use the ToolHive MCP tools (`flux_*`, `kubernetes_*`, `talos_*`) for live cluster
inspection and reconciliation; use `github_*` for PRs and `konflate` for
rendered-diff PR review evidence.
