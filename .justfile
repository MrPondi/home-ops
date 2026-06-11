#!/usr/bin/env -S just --justfile

set lazy
set quiet
set shell := ['bash', '-euo', 'pipefail', '-c']

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
    minijinja-cli --env "{{ file }}" {{ args }} | vals eval -f -

[private]
[script]
bitwarden:
    STATUS=$(curl -s http://localhost:8087/status | jq -r '.data.template.status' 2>/dev/null || echo "no_service")

    if [ "$STATUS" != "unlocked" ]; then
        just bitwarden-auth "$STATUS"
    fi

[private]
[script]
bitwarden-auth status:
    export BW_PASSWORD="$(gum input --password --placeholder="..." --prompt="Master password: " --header="Bitwarden CLI Login" --cursor.foreground="81")"

    if [ "{{ status }}" = "locked" ]; then
        JSON_BODY=$(jq -n --arg password "$BW_PASSWORD" '{password: $password}')

        RESPONSE=$(curl -s -X POST http://localhost:8087/unlock \
            -H "Content-Type: application/json" \
            -d "$JSON_BODY")

        if [ "$(printf '%s' "$RESPONSE" | jq -r '.success')" != "true" ]; then
            just log fatal "Failed to unlock Bitwarden vault via API" "stage" "$(basename "$0")"
        fi
        sleep 0.25
    else
        if ! BW_SESSION="$(bw unlock --raw --passwordenv BW_PASSWORD > /dev/null 2>&1)"; then
            just log fatal "Failed to unlock Bitwarden vault" "stage" "$(basename "$0")"
        fi
        export BW_SESSION

        pkill -f "bw serve" || true
        nohup bw serve < /dev/null > /dev/null 2>&1 &
        sleep 0.25
    fi
