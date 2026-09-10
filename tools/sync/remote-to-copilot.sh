#!/usr/bin/env bash
# Generate workspace .github content directly from the published skills repository.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE=""
MODE=""
REF="main"
PRUNE=""

usage() {
  cat <<'EOF'
Usage:
  remote-to-copilot.sh [workspace] [--dry-run|--check] [--prune] [--ref REF]

Downloads the remote source into temporary staging and generates workspace
.github content without creating or modifying workspace .claude.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run|--check)
      [ -z "$MODE" ] || {
        echo "error: --dry-run and --check are mutually exclusive." >&2
        exit 2
      }
      MODE="$1"
      ;;
    --prune)
      PRUNE="--prune"
      ;;
    --ref)
      shift
      REF="${1:?--ref needs a value}"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      echo "error: unknown option: $1" >&2
      exit 2
      ;;
    *)
      [ -z "$WORKSPACE" ] || {
        echo "error: only one workspace path may be provided." >&2
        exit 2
      }
      WORKSPACE="$1"
      ;;
  esac
  shift
done

WORKSPACE="${WORKSPACE:-$PWD}"
if ! WORKSPACE="$(cd "$WORKSPACE" 2>/dev/null && pwd)"; then
  echo "error: workspace directory not found." >&2
  exit 1
fi

[ -x "$SCRIPT_DIR/remote-to-workspace.sh" ] || {
  echo "error: missing implementation: $SCRIPT_DIR/remote-to-workspace.sh" >&2
  exit 1
}
[ -f "$SCRIPT_DIR/copilot/generate.py" ] || {
  echo "error: missing implementation: $SCRIPT_DIR/copilot/generate.py" >&2
  exit 1
}
command -v python3 >/dev/null 2>&1 && python3 --version >/dev/null 2>&1 || {
  echo "error: python3 not found or not executable." >&2
  exit 1
}

STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

"$SCRIPT_DIR/remote-to-workspace.sh" "$STAGING" --ref "$REF"
python3 "$SCRIPT_DIR/copilot/generate.py" \
  --source "$STAGING/.claude" \
  --target "$WORKSPACE/.github" \
  ${MODE:+"$MODE"} \
  ${PRUNE:+"$PRUNE"}
