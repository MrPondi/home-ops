#!/bin/bash
set -eo pipefail

# 1. Dependency check
for cmd in curl jq gum; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "Error: Required command '$cmd' is not installed." >&2
    exit 1
  fi
done

# 2. Environment variables
SERVER="https://jellyfin.pondi.dev"
API_KEY="${JELLYFIN_API_KEY:?Error: JELLYFIN_API_KEY is not set}"
USER_ID="${JELLYFIN_USER_ID:?Error: JELLYFIN_USER_ID is not set}"
CONCURRENCY=8

TMP_JSON=$(mktemp)
trap 'tput cnorm 2>/dev/null || true; rm -f "$TMP_JSON"' EXIT INT TERM

# Header
gum style \
  --border rounded \
  --margin "1 0" \
  --padding "0 2" \
  --border-foreground 212 \
  --bold "🎬 Jellyfin Missing Actor Image Sync"

# 3. Query Jellyfin using Header Authentication
gum spin --spinner dot --title "Querying Jellyfin for actors without images..." -- \
  curl -sf -H "X-Emby-Token: $API_KEY" "$SERVER/emby/Persons" -o "$TMP_JSON"

# Parse IDs into a Bash array
readarray -t ACTOR_IDS < <(jq -r '.Items[]? | select(.ImageTags.Primary == null) | .Id' "$TMP_JSON")
TOTAL=${#ACTOR_IDS[@]}

if [ "$TOTAL" -eq 0 ]; then
  gum style --foreground 2 --bold "✔ All actors already have images! Nothing to do."
  exit 0
fi

gum style --foreground 99 "Found $TOTAL actors missing images. Syncing ($CONCURRENCY parallel workers)..."
echo ""

# 4. Parallel Sync with Single-Line Progress Bar
tput civis
BAR_LEN=30
SUCCESS=0
FAILED=0
PROCESSED=0

PINK="\033[38;5;212m"
GREEN="\033[38;5;42m"
GRAY="\033[38;5;240m"
RESET="\033[0m"

# Avoid pipeline subshell using process substitution
while read -r HTTP_STATUS; do
  PROCESSED=$((PROCESSED + 1))
  if [[ "$HTTP_STATUS" =~ ^2[0-9]{2}$ ]]; then
    SUCCESS=$((SUCCESS + 1))
  else
    FAILED=$((FAILED + 1))
  fi

  PCT=$(( PROCESSED * 100 / TOTAL ))
  FILLED=$(( PROCESSED * BAR_LEN / TOTAL ))
  EMPTY=$(( BAR_LEN - FILLED ))

  # Construct bars safely
  BAR_STR=$(printf "%0.s█" $(seq 1 $FILLED 2>/dev/null) || true)
  EMPTY_STR=$(printf "%0.s░" $(seq 1 $EMPTY 2>/dev/null) || true)

  # Overwrite current line cleanly with \r
  printf "\r\033[K${PINK}[%d/%d]${RESET} %3d%% [${GREEN}%s${GRAY}%s${RESET}]" \
    "$PROCESSED" "$TOTAL" "$PCT" "$BAR_STR" "$EMPTY_STR"
done < <(
  printf "%s\n" "${ACTOR_IDS[@]}" | xargs -I {} -P "$CONCURRENCY" \
    curl -s -o /dev/null -w "%{http_code}\n" \
      -H "X-Emby-Token: $API_KEY" \
      "$SERVER/Users/$USER_ID/Items/{}"
)

tput cnorm
echo -e "\n"

# 5. Result Summary
if [ "$FAILED" -eq 0 ]; then
  gum style \
    --border rounded \
    --padding "0 2" \
    --border-foreground 42 \
    --foreground 42 \
    --bold "✔ Finished! Successfully updated all $SUCCESS actors."
else
  gum style \
    --border rounded \
    --padding "0 2" \
    --border-foreground 214 \
    --foreground 214 \
    --bold "⚠ Finished with issues: $SUCCESS updated, $FAILED failed."
fi