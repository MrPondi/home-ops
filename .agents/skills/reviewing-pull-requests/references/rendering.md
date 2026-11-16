# Rendering a HelmRelease with flate

When a chart version or a HelmRelease's values change, render the
HelmRelease with this repository's values, from the repository root.

This repository pins flate v0.6.5 (`.mise/config.toml`, `.kritika.yaml`).
Upstream's version of this file is written for flate 0.7.x, which cannot
render this repository's layout yet; keep to the commands below.

Render from the whole tree and name the namespace. Nearly every
Kustomization here depends on one in another namespace
(`external-secrets-store`, the database operators), and the namespace
overlays pull in `../../components`, so a namespace directory alone as the
path reports the HelmRelease as blocked:

```
flate build hr <name> -n <namespace> --path kubernetes/apps --no-progress
```

A render takes under a second and about 400 MB.

kritika's checkout has no git history, so only the head renders. With
history, do not use `flate diff --base`: v0.6.5 materializes only part of
the base revision here and fails to find `kubernetes/apps`. Render the base
from a worktree and diff the two renders:

```
tmp=$(mktemp -d)
git worktree add --detach "$tmp/base" origin/main
flate build hr <name> -n <namespace> --path "$tmp/base/kubernetes/apps" --no-progress > "$tmp/base.yaml"
flate build hr <name> -n <namespace> --path kubernetes/apps --no-progress > "$tmp/head.yaml"
diff -u "$tmp/base.yaml" "$tmp/head.yaml"
git worktree remove --force "$tmp/base"
```

flate reports every failure in the namespace, not only the requested
HelmRelease's, and exits nonzero for any of them. Only a failure the change
caused is a finding on the changed line: a value the chart's schema
rejects, a template that errors on this repository's values. A failure of
another HelmRelease, or a source flate failed to fetch, says nothing about
the change.

A render that succeeds is an offline approximation of what the cluster
applies: CRDs and Secrets are left out, patches Flux applies from a parent
Kustomization are not, and templates that branch on Kubernetes
capabilities see flate's bundled version, not the cluster's. Within that,
take the label values, resource names and ports the search for
dependents needs from the render rather than from a reading of the template.
When the whole output is too long, narrow it with `--show-only <template
path>` or filter the rendered YAML. Where only the head renders, what the
base produced is read upstream, or from the names this repository already
refers to.
