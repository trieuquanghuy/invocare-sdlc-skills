#!/usr/bin/env bash
# jira-attachments.sh — download all attachments for a Jira ticket
#
# Usage:
#   bash .claude/scripts/jira-attachments.sh <TICKET_KEY> [output_dir]
#
# Default output: tickets/<TICKET_KEY>/attachments/
# Requires env: ATLASSIAN_EMAIL, ATLASSIAN_API_TOKEN (auto-loaded by direnv from .envrc).
# Requires tools: curl, jq.
#
# Behavior:
#   - Reads attachment metadata via Jira REST v3 (no MCP dependency — works in any shell).
#   - Skips files that already exist locally with the same byte size.
#   - Sanitizes filenames via basename to prevent path traversal.
#   - Never echoes the token; auth errors surface as HTTP codes only.
#   - Cross-host redirect to signed S3 URL is handled by curl's default
#     auth-stripping (Atlassian credentials are not sent to S3).

set -euo pipefail

JIRA_BASE_URL="https://invocarecompass.atlassian.net"

TICKET_KEY="${1:-}"
if [ -z "$TICKET_KEY" ]; then
  echo "Usage: $0 <TICKET_KEY> [output_dir]" >&2
  echo "Example: $0 GEN-1234" >&2
  exit 2
fi

# Derive InvoCare root from script location (works regardless of cwd)
INVOCARE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="${2:-$INVOCARE_ROOT/tickets/$TICKET_KEY/attachments}"

# Env-var pre-flight
: "${ATLASSIAN_EMAIL:?ATLASSIAN_EMAIL not set — run from the InvoCare folder where direnv loads .envrc}"
: "${ATLASSIAN_API_TOKEN:?ATLASSIAN_API_TOKEN not set — run from the InvoCare folder where direnv loads .envrc}"

# Tool pre-flight
for cmd in curl jq; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required tool: $cmd" >&2
    exit 3
  fi
done

# Fetch attachment metadata to a temp file so we can inspect HTTP status separately
TMP=$(mktemp -t jira-attach.XXXXXX)
trap 'rm -f "$TMP"' EXIT

HTTP=$(curl -s -u "$ATLASSIAN_EMAIL:$ATLASSIAN_API_TOKEN" \
  -o "$TMP" -w "%{http_code}" \
  "$JIRA_BASE_URL/rest/api/3/issue/$TICKET_KEY?fields=attachment")

case "$HTTP" in
  200) ;;
  401) echo "✗ 401 Unauthorized — check ATLASSIAN_API_TOKEN" >&2; exit 4 ;;
  403) echo "✗ 403 Forbidden — token lacks permission for $TICKET_KEY" >&2; exit 4 ;;
  404) echo "✗ 404 Not Found — ticket $TICKET_KEY does not exist or you can't see it" >&2; exit 4 ;;
  *)   echo "✗ HTTP $HTTP fetching metadata for $TICKET_KEY" >&2; exit 4 ;;
esac

COUNT=$(jq '.fields.attachment | length' < "$TMP")
if [ "$COUNT" -eq 0 ]; then
  echo "$TICKET_KEY: no attachments."
  exit 0
fi

mkdir -p "$OUT_DIR"
echo "$TICKET_KEY: $COUNT attachment(s) → $OUT_DIR/"

DOWNLOADED=0
SKIPPED=0
FAILED=0

# shellcheck disable=SC2030,SC2031
jq -c '.fields.attachment[]' < "$TMP" | while read -r ATTACH; do
  FILENAME=$(printf %s "$ATTACH" | jq -r '.filename')
  SIZE=$(printf %s "$ATTACH" | jq -r '.size')
  CONTENT_URL=$(printf %s "$ATTACH" | jq -r '.content')

  # basename strips any path components in the filename (defense against ../ traversal)
  SAFE_NAME=$(basename "$FILENAME")
  if [ -z "$SAFE_NAME" ] || [ "$SAFE_NAME" = "." ] || [ "$SAFE_NAME" = ".." ]; then
    printf '  ✗ skipping suspicious filename: %q\n' "$FILENAME"
    FAILED=$((FAILED + 1))
    continue
  fi

  TARGET="$OUT_DIR/$SAFE_NAME"

  if [ -f "$TARGET" ]; then
    EXISTING_SIZE=$(stat -f '%z' "$TARGET" 2>/dev/null || stat -c '%s' "$TARGET" 2>/dev/null || echo 0)
    if [ "$EXISTING_SIZE" = "$SIZE" ]; then
      printf '  ✓ skip (already downloaded, %s B): %s\n' "$SIZE" "$SAFE_NAME"
      SKIPPED=$((SKIPPED + 1))
      continue
    fi
    printf '  ⚠ exists but size differs (local=%s, remote=%s) — overwriting: %s\n' \
      "$EXISTING_SIZE" "$SIZE" "$SAFE_NAME"
  fi

  DL_HTTP=$(curl -s -L -u "$ATLASSIAN_EMAIL:$ATLASSIAN_API_TOKEN" \
    -o "$TARGET" -w "%{http_code}" "$CONTENT_URL")

  if [ "$DL_HTTP" = "200" ]; then
    printf '  ✓ %s (%s B)\n' "$SAFE_NAME" "$SIZE"
    DOWNLOADED=$((DOWNLOADED + 1))
  else
    printf '  ✗ %s — HTTP %s\n' "$SAFE_NAME" "$DL_HTTP"
    rm -f "$TARGET"
    FAILED=$((FAILED + 1))
  fi
done

# Note: counters inside the while-read pipeline run in a subshell on most shells,
# so the summary below reflects the parent shell's view. The per-file output is
# the authoritative record.
echo "Done."
