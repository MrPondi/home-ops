#!/usr/bin/env -S just --justfile

set lazy
set quiet
set shell := ['bash', '-euo', 'pipefail', '-c']
set script-interpreter := ['bash', '-euo', 'pipefail']

# Bootstrap Recipes
[group: 'Bootstrap']
mod bootstrap "bootstrap"

# Kube Recipes
[group: 'Kube']
mod kube "kubernetes"

# Talos Recipes
[group: 'Talos']
mod talos "talos"

[private]
default:
    just -l

[private]
log lvl msg *args:
    gum log -t rfc3339 -s -l "{{ lvl }}" "{{ msg }}" {{ args }}

[private]
template file *args: bitwarden
    minijinja-cli "{{ file }}" {{ args }} | vals eval -f -

[private]
[script]
bitwarden:
    STATUS=$(curl -s -f http://localhost:8087/status | jq -r '.data.template.status' 2>/dev/null || echo "no_service")

    if [ "$STATUS" != "unlocked" ]; then
        just bitwarden-auth "$STATUS"
    fi

[private]
[script]
bitwarden-auth status:
    export BW_PASSWORD="$(gum input --password --placeholder="..." --prompt="Master password: " --header="Bitwarden CLI Login ({{ status }})" --cursor.foreground="81")"

    if [ "{{ status }}" != "locked" ]; then
        pkill -f "bw serve" || true
        nohup bw serve < /dev/null > /dev/null 2>&1 &
        if ! curl -s --retry-connrefused --retry 5 --retry-delay 1 http://localhost:8087/status > /dev/null; then
            just log fatal "Bitwarden server failed to start" "stage" "$(basename "$0")"
        fi
    fi

    JSON_BODY=$(jq -n --arg password "$BW_PASSWORD" '{password: $password}')

    RESPONSE=$(curl -s -X POST http://localhost:8087/unlock \
        -H "Content-Type: application/json" \
        -d "$JSON_BODY")

    if [ "$(printf '%s' "$RESPONSE" | jq -r '.success')" != "true" ]; then
        just log fatal "Failed to unlock Bitwarden vault" "stage" "$(basename "$0")"
    fi
