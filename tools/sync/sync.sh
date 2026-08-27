#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'EOF'
Usage:
  ./tools/sync/sync.sh remote-to-workspace [workspace] [--dry-run] [--ref REF] [--force]
  ./tools/sync/sync.sh workspace-to-checkout [workspace] [--dry-run]
  ./tools/sync/sync.sh workspace-to-copilot [workspace] [--dry-run|--check] [--prune]
  ./tools/sync/sync.sh remote-to-copilot [workspace] [--dry-run|--check] [--prune] [--ref REF]
  ./tools/sync/sync.sh help
EOF
}

require_executable() {
  [ -x "$1" ] || {
    echo "error: missing implementation: $1" >&2
    exit 1
  }
}

require_file() {
  [ -f "$1" ] || {
    echo "error: missing implementation: $1" >&2
    exit 1
  }
}

COMMAND="${1:-}"
[ $# -eq 0 ] || shift

case "$COMMAND" in
  help|-h|--help)
    usage
    ;;
  remote-to-workspace)
    require_executable "$SCRIPT_DIR/remote-to-workspace.sh"
    exec "$SCRIPT_DIR/remote-to-workspace.sh" "$@"
    ;;
  workspace-to-checkout)
    require_executable "$SCRIPT_DIR/workspace-to-checkout.sh"
    exec "$SCRIPT_DIR/workspace-to-checkout.sh" "$@"
    ;;
  workspace-to-copilot)
    command -v python3 >/dev/null || {
      echo "error: python3 not found." >&2
      exit 1
    }
    require_file "$SCRIPT_DIR/copilot/generate.py"
    exec python3 "$SCRIPT_DIR/copilot/generate.py" "$@"
    ;;
  remote-to-copilot)
    require_executable "$SCRIPT_DIR/remote-to-copilot.sh"
    exec "$SCRIPT_DIR/remote-to-copilot.sh" "$@"
    ;;
  "")
    usage >&2
    exit 2
    ;;
  *)
    echo "error: unknown command: $COMMAND" >&2
    usage >&2
    exit 2
    ;;
esac
