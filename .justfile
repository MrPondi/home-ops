#!/usr/bin/env -S just --justfile

set quiet := true
set shell := ['bash', '-euo', 'pipefail', '-c']

mod bootstrap
mod kube 'kubernetes'
mod talos

[private]
default:
    just -l

[private]
log lvl msg *args:
    gum log -t rfc3339 -s -l "{{ lvl }}" "{{ msg }}" {{ args }}

[private]
template file *args:
    minijinja-cli "{{ file }}" {{ args }}

[doc('Force Flux to pull in changes from your Git repository')]
reconcile:
    flux --namespace flux-system reconcile kustomization flux-system --with-source
