#!/usr/bin/env bash
# Generate workspace .github content directly from the published skills repository.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE=""
MODE=""
REF="main"
PRUNE=""
SKILLS_MODE="mirror"

usage() {
  cat <<'EOF'
Usage:
  remote-to-copilot.sh [workspace] [--dry-run|--check|--compatibility-report]
                      [--prune] [--skills-mode mirror] [--ref REF]

Downloads the remote source into temporary staging and generates workspace
.github content without creating or modifying workspace .claude.
Native skill reuse is local-only: temporary remote staging cannot be reused.
Compatibility reports are read-only JSON; download progress goes to stderr.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run|--check|--compatibility-report)
      [ -z "$MODE" ] || {
        echo "error: --dry-run, --check, and --compatibility-report are mutually exclusive." >&2
        exit 2
      }
      MODE="$1"
      ;;
    --prune)
      PRUNE="--prune"
      ;;
    --skills-mode)
      shift
      [ $# -gt 0 ] || {
        echo "error: --skills-mode needs a value." >&2
        exit 2
      }
      SKILLS_MODE="$1"
      ;;
    --skills-mode=*)
      SKILLS_MODE="${1#*=}"
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

case "$SKILLS_MODE" in
  mirror) ;;
  native)
    echo "error: native skills cannot reuse temporary remote staging; use workspace-to-copilot with persistent .claude content." >&2
    exit 2
    ;;
  *)
    echo "error: --skills-mode must be mirror or native." >&2
    exit 2
    ;;
esac

if [ -n "$PRUNE" ] && { [ "$MODE" = "--check" ] || [ "$MODE" = "--compatibility-report" ]; }; then
  echo "error: $MODE and --prune cannot be combined." >&2
  exit 2
fi

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
python3 -c 'import yaml' >/dev/null 2>&1 || {
  echo "error: PyYAML is required; run python3 -m pip install -r \"$SCRIPT_DIR/copilot/requirements.txt\"." >&2
  exit 1
}

STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

if [ "$MODE" = "--compatibility-report" ]; then
  "$SCRIPT_DIR/remote-to-workspace.sh" "$STAGING" --ref "$REF" >&2
else
  "$SCRIPT_DIR/remote-to-workspace.sh" "$STAGING" --ref "$REF"
fi
python3 "$SCRIPT_DIR/copilot/generate.py" \
  --source "$STAGING/.claude" \
  --target "$WORKSPACE/.github" \
  --skills-mode "$SKILLS_MODE" \
  ${MODE:+"$MODE"} \
  ${PRUNE:+"$PRUNE"}
