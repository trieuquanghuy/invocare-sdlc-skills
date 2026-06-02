#!/usr/bin/env bash
#
# contribute-skills.sh — sync your workspace .claude/ edits UP into your repo clone (one way).
#
# For CONTRIBUTORS who have cloned this repo. It copies the shared skill set from a
# workspace .claude/ into the clone's working tree, then prints the commit/PR steps.
# (To go the other way — install/update a workspace FROM the repo — use update-skills.sh.)
#
# The clone is the directory this script lives in, so you never pass the repo path.
# The workspace defaults to the clone's parent directory (the common layout where the
# clone sits inside the workspace); pass a path to override.
#
# Usage:
#   ./contribute-skills.sh [path-to-workspace] [--dry-run]
#
#   path-to-workspace   defaults to the clone's parent dir; pass it if your clone lives elsewhere
#   --dry-run           show what would change; write nothing (recommended first)
#
# Never deletes (a retired skill leaves a stale copy until removed by hand). Never commits:
# it updates the clone's working tree, then prints the branch/commit/PR steps — you craft the PR.
#
# Requires: rsync.
set -euo pipefail
# Disable pathname expansion: the exclude patterns below (*.bak, .git*, *.example)
# are passed unquoted so they word-split into separate rsync flags — without -f the
# shell would glob them against the CWD and corrupt the fence. Word-splitting (needed
# for $EXC and $SHARED) still works under -f; only globbing is off.
set -f

CLONE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS=""
DRY=""

while [ $# -gt 0 ]; do
  case "$1" in
    push)      : ;;                               # legacy no-op: this script is push-only now
    pull)      echo "error: 'pull' (repo → workspace) is no longer supported — this script only syncs .claude → repo." >&2
               echo "       To install/update a workspace FROM the repo, use update-skills.sh." >&2; exit 1 ;;
    --dry-run) DRY="--dry-run" ;;
    -h|--help) sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*)        echo "unknown option: $1" >&2; exit 1 ;;
    *)         WS="$1" ;;
  esac
  shift
done

command -v rsync >/dev/null || { echo "error: rsync not found." >&2; exit 1; }

# Sanity: this script must live inside an invocare-sdlc-skills clone.
[ -d "$CLONE/skills" ] && [ -f "$CLONE/update-skills.sh" ] || {
  echo "error: $CLONE is not an invocare-sdlc-skills clone (expected skills/ + update-skills.sh)." >&2; exit 1; }

# Workspace defaults to the clone's parent dir (clone-inside-workspace layout); pass a path to override.
WS="${WS:-$(dirname "$CLONE")}"
if ! WS="$(cd "$WS" 2>/dev/null && pwd)"; then
  echo "error: workspace directory not found (pass the path explicitly)." >&2; exit 1
fi
CLAUDE="$WS/.claude"

# The shared payload — the repo root maps 1:1 onto .claude/. Only these items ever cross;
# everything else in .claude (settings.local.json, .mcp.json, skills/_local/, scratch dirs)
# is left untouched simply by not being listed. The list is read from shared-manifest.txt —
# the SINGLE SOURCE OF TRUTH, also read by update-skills.sh. A built-in default covers a clone
# that predates the manifest.
SHARED_DEFAULT="rules agents scripts skills CLAUDE.md HOW-TO-USE.md"
if [ -f "$CLONE/shared-manifest.txt" ]; then
  SHARED="$(grep -vE '^[[:space:]]*(#|$)' "$CLONE/shared-manifest.txt" | tr '\n' ' ')"
else
  SHARED="$SHARED_DEFAULT"
fi

# The fence — personal / per-machine / repo-meta patterns never cross. Patterns are
# filename-based (no spaces), so unquoted word-splitting into rsync flags is safe and keeps
# us off bash arrays (macOS bash 3.2).
EXC="--exclude .git* --exclude settings.local.json --exclude .mcp.json"
EXC="$EXC --exclude .update-backup-*/ --exclude CLAUDE.md.backup-* --exclude .skills-sync-state --exclude .skills-sync-manifest"
EXC="$EXC --exclude .DS_Store --exclude *.bak --exclude *.drive"
EXC="$EXC --exclude README.md --exclude CONTRIBUTING.md --exclude ONBOARDING.md"
EXC="$EXC --exclude update-skills.sh --exclude contribute-skills.sh --exclude *.example"

echo "Sync:      .claude -> clone (one way)"
echo "Clone:     $CLONE"
echo "Workspace: $CLAUDE"
echo "Mode:      ${DRY:+DRY-RUN (no changes written)}${DRY:-apply}"
echo

[ -d "$CLAUDE" ] || {
  echo "error: workspace .claude not found: $CLAUDE" >&2
  echo "       Pass the right workspace path, or install it first with update-skills.sh." >&2; exit 1; }

# Collect the shared items that exist in .claude (full paths; an array keeps paths with spaces safe).
SRCS=()
for item in $SHARED; do
  if [ -e "$CLAUDE/$item" ]; then
    SRCS+=( "$CLAUDE/$item" )
  elif [ "$item" = "HOW-TO-USE.md" ]; then
    echo "note: HOW-TO-USE.md not found at .claude root — skipped."
    echo "      (the canonical layout maps .claude root <-> repo root; keep it at .claude/HOW-TO-USE.md.)"
  fi
done
[ "${#SRCS[@]}" -gt 0 ] || { echo "error: no shared items found in $CLAUDE — nothing to sync." >&2; exit 1; }

# One rsync of every item into the clone root, so the change list shows FULL paths
# (skills/task-status/SKILL.md, not task-status/SKILL.md). No --delete; git in the clone is the
# safety net. skills/_local/ is personal and HOW-TO-USE.md doesn't belong under skills/.
# We itemize, then keep ONLY real content changes — new files (code has +++++++) and modified
# files (>f...) — dropping directory entries and metadata-only churn (mtime/perms) that git
# ignores anyway. That turns a wall of `.f..t....` lines into just the files that matter.
SKILL_EXC="--exclude skills/_local/*** --exclude skills/HOW-TO-USE.md"
RAW="$(rsync -ac --itemize-changes $DRY $EXC $SKILL_EXC "${SRCS[@]}" "$CLONE/")"
SYNCED="$(printf '%s\n' "$RAW" | grep -E '^[<>]f' \
  | sed -E 's/^[<>]f[^ ]*\+\+\+\+\+\+\+ /  new      /; s/^[<>]f[^ ]* /  updated  /' || true)"
NEW_N="$(printf '%s\n' "$SYNCED" | grep -c '^  new ' || true)"
UPD_N="$(printf '%s\n' "$SYNCED" | grep -c '^  updated ' || true)"

echo
if [ -z "$SYNCED" ]; then
  echo "✓ Already in sync — no file contents differ between .claude and the clone. Nothing to push."
  exit 0
fi

if [ -n "$DRY" ]; then
  echo "Would sync to the repo — $NEW_N new, $UPD_N updated  (.claude -> clone):"
  printf '%s\n' "$SYNCED"
  echo
  echo "[dry-run] nothing written. Re-run without --dry-run to apply."
  exit 0
fi

echo "✓ Synced to the clone — $NEW_N new, $UPD_N updated  (.claude -> clone):"
printf '%s\n' "$SYNCED"
echo
echo "Nothing was committed — review and open a PR:"
echo
git -C "$CLONE" status --short 2>/dev/null | sed 's/^/    /' || true
echo
echo "  cd \"$CLONE\""
echo "  git switch -c fix/<short-description>"
echo "  git add -p && git commit -m \"fix(<skill>): <what changed>\"   # subject-only, no attribution"
echo "  git push -u origin HEAD && gh pr create --fill"
echo "  (full guide: CONTRIBUTING.md)"
