# Repository review policy

House rules for judging a change here. `AGENTS.md` remains the source for conventions (namespace injection, label-driven components, key ordering); a pattern it documents as intentional is not a finding.

## HelmRelease requirements

- Every application is a Flux `HelmRelease` with `spec.chartRef` pointing at the **per-app `OCIRepository`** (named after the app, in its own `ocirepository.yaml`) pinned by `ref.tag`, and a `spec.interval`.
- `install`/`upgrade`/`rollback`/`remediation` defaults are patched globally by the root `flux-system` Kustomization — do not add them per-app, and do not flag their absence.
- `metadata.namespace` is **never** set inline on `HelmRelease`/`Kustomization` resources (see Conventions) — reviewers MUST NOT flag its absence.
- Postgres/Dragonfly components arrive via labels (see "Label-driven components") — do not flag their absence from `spec.components`.

## Secret management rules

- **NEVER** commit plain-text secrets, tokens or keys in Git — all secrets go through `external-secrets` with the `bitwarden-secretsmanager` `ClusterSecretStore`; templated values via `substituteFrom` Secrets created from ExternalSecrets.
- Talos (`talos/*.yaml.j2` + `vals`/bw-serve) and Terraform (`.sops.yaml` + `age.key`) resolve secrets at render time — this is the intended pattern; do not convert them to external-secrets.

## Image & digest policy

- Container images: prefer `@sha256:` digests over version tags for reproducibility.
- OCI chart artifacts pulled via `OCIRepository` are **exempt**: pin by tag/version.
- Reject updates from untrusted registries; prefer GHCR.io and registry.k8s.io, Docker Hub only as fallback (avoid it for critical infrastructure components).

## Breaking change detection

Request changes if:

- API version changes (e.g. `apps/v1beta1` → `apps/v1`), deprecated field usage, or major version bumps without justification
- CRD changes or custom resource modifications
- Network policy or security context relaxations

For major chart/app bumps, read the upstream release notes (context7 / GitHub releases) and cite the relevant breaking changes.

## Kubernetes ↔ Talos compatibility

Talos pins the node OS and kubelet together; tuppr drives upgrades (`kubernetes/apps/system-upgrade/tuppr/`). When a PR bumps the Kubernetes version (kubelet image, `KubernetesUpgrade` resource, or the `kubernetes` Renovate group), you MUST:

1. Read the deployed Talos version from `kubernetes/apps/system-upgrade/tuppr/upgrades/talosupgrade.yaml` (see "Versions").
2. Confirm the new Kubernetes version is supported on that Talos release against Talos's published support matrix — search the web for "talos `<version>` kubernetes support matrix" (docs live at `docs.siderolabs.com`).
3. Cite the matrix in the review. Do not approve a Kubernetes bump on "patch release" reasoning without confirming Talos supports it.
