#!/usr/bin/env bash
#
# update-skills.sh — install or update the InvoCare shared skills in a workspace .claude/.
#
# ONE command, no clone, no GitHub auth (the repo is public — fetched over plain https).
# Run it the first time to install, re-run anytime to update. Idempotent.
#
# Quickest path — cd into the workspace, then run with NO arguments (workspace = current dir):
#   cd <your-workspace>
#   curl -fsSL https://raw.githubusercontent.com/trieuquanghuy/invocare-sdlc-skills/main/update-skills.sh | bash
#
# Or pass a path / flags explicitly (when piping, flags go after `-s --`):
#   ./update-skills.sh [path-to-workspace] [--dry-run] [--ref <branch|tag>] [--force]
#
#   --dry-run   show what would change; write nothing (recommended on first run)
#   --ref <x>   install a specific branch or CalVer tag (default: main)
#   --force     re-sync even when already up to date (skips the up-to-date short-circuit)
#
# Before downloading, it compares the repo's latest commit to the one it last synced
# (recorded in .claude/.skills-sync-state); on a match it prints "already up to date" and
# exits without downloading. Otherwise it makes .claude/ match the repo's shared set, backs
# up any file it overwrites, never deletes, and never touches your settings.local.json /
# .mcp.json / skills/_local/. On first install it also drops the *.example config templates
# into .claude/ so you can create your own settings.local.json + .mcp.json.
#
# Requires: curl, tar, rsync (all preinstalled on macOS). gh is only a fallback.
set -euo pipefail

OWNER_REPO="trieuquanghuy/invocare-sdlc-skills"
REF="main"
DRY=""
WS=""
FORCE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY="--dry-run" ;;
    --ref)     shift; REF="${1:?--ref needs a value}" ;;
    --force)   FORCE=1 ;;
    -h|--help) sed -n '2,26p' "$0" 2>/dev/null | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*)        echo "unknown option: $1" >&2; exit 1 ;;
    *)         WS="$1" ;;
  esac
  shift
done

# No workspace given? default to the current directory — cd into your workspace and run.
WS="${WS:-$PWD}"
if ! WS_ABS="$(cd "$WS" 2>/dev/null && pwd)"; then
  echo "error: workspace directory not found: $WS" >&2; exit 1
fi
WS="$WS_ABS"
command -v rsync >/dev/null || { echo "error: rsync not found." >&2; exit 1; }
command -v tar   >/dev/null || { echo "error: tar not found." >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Repo:      $OWNER_REPO @ $REF (public)"
echo "Workspace: $WS"
echo "Mode:      ${DRY:+DRY-RUN (no changes written)}${DRY:-apply}"
echo

# 0. Up-to-date check. Resolve the ref's latest commit SHA (cheap — no tarball) and compare
#    it to the SHA recorded after the last sync. On a match (and no --force) skip the whole
#    download. SHA-fetch failure is non-fatal: fall through to the normal download path.
STAMP="$WS/.claude/.skills-sync-state"
MANIFEST="$WS/.claude/.skills-sync-manifest"   # files installed at last sync (per-machine)
REMOTE_SHA=""
if command -v curl >/dev/null; then
  REMOTE_SHA="$(curl -fsSL -H 'Accept: application/vnd.github.sha' "https://api.github.com/repos/$OWNER_REPO/commits/$REF" 2>/dev/null || true)"
fi
if [ -z "$REMOTE_SHA" ] && command -v gh >/dev/null; then
  REMOTE_SHA="$(gh api "repos/$OWNER_REPO/commits/$REF" --jq '.sha' 2>/dev/null || true)"
fi
# Accept only a clean 40-char hex SHA; anything else (HTML error page, rate-limit JSON) = unknown.
case "$REMOTE_SHA" in
  "" | *[!0-9a-fA-F]*) REMOTE_SHA="" ;;
  *) [ "${#REMOTE_SHA}" -eq 40 ] || REMOTE_SHA="" ;;
esac

if [ -z "$FORCE" ] && [ -n "$REMOTE_SHA" ] && [ -f "$STAMP" ] && [ -f "$MANIFEST" ]; then
  read -r STAMP_REF STAMP_SHA _ < "$STAMP" 2>/dev/null || true
  if [ "${STAMP_REF:-}" = "$REF" ] && [ "${STAMP_SHA:-}" = "$REMOTE_SHA" ]; then
    # Remote unchanged. Only skip the download if the install is still COMPLETE — every file
    # recorded at last sync still exists. A deleted skill/file is local drift, so fall through
    # and re-sync to restore it. (No manifest yet → outer guard fails → re-sync to create one.)
    MISSING=0
    while IFS= read -r rel; do
      [ -n "$rel" ] || continue
      [ -e "$WS/.claude/$rel" ] || MISSING=$((MISSING + 1))
    done < "$MANIFEST"
    if [ "$MISSING" -eq 0 ]; then
      echo "Already up to date: $REF @ ${REMOTE_SHA:0:7} — last synced from this commit."
      echo "  Use --force to re-sync anyway (e.g. to restore locally-changed files)."
      exit 0
    fi
    echo "Up to date with $REF @ ${REMOTE_SHA:0:7}, but $MISSING tracked file(s) missing locally — re-syncing to restore them."
  fi
fi

# 1. Download the repo tarball. Public repo => plain curl, no auth. Try branch, then tag,
#    then fall back to gh (covers a private repo, or an environment where curl is blocked).
echo "Downloading latest skill set…"
TGZ="$TMP/skills.tgz"
if   command -v curl >/dev/null && curl -fsSL "https://codeload.github.com/$OWNER_REPO/tar.gz/refs/heads/$REF" -o "$TGZ" 2>/dev/null; then :
elif command -v curl >/dev/null && curl -fsSL "https://codeload.github.com/$OWNER_REPO/tar.gz/refs/tags/$REF"  -o "$TGZ" 2>/dev/null; then :
elif command -v gh   >/dev/null && gh api "repos/$OWNER_REPO/tarball/$REF" > "$TGZ" 2>/dev/null; then :
else
  echo "error: could not download $OWNER_REPO@$REF." >&2
  echo "  Checked the public tarball for branch and tag '$REF'." >&2
  echo "  • Wrong branch/tag? pass --ref <branch|tag>." >&2
  echo "  • Repo is private? run 'gh auth login' and re-run (gh fallback)." >&2
  echo "  • Repo empty / not pushed yet? nothing to install until 'main' has content." >&2
  exit 1
fi
mkdir -p "$TMP/x"
tar -xzf "$TGZ" -C "$TMP/x" --strip-components=1   # drop the wrapper dir (owner-repo-ref/)

# 2. Sync the SHARED payload into .claude/.
#    The shared set is read from shared-manifest.txt (the SINGLE SOURCE OF TRUTH, also
#    read by contribute-skills.sh — one list, no "keep the two in sync" coupling). It is
#    an ALLOWLIST: only the listed top-level items are synced, so a new repo file is never
#    shipped to consumers until it's added to the manifest. A built-in default covers an
#    older tarball that predates the manifest.
#    -c (checksum) avoids spurious backups from the tarball's fresh extract mtimes;
#    --backup keeps every overwritten file; NO --delete, so personal skills survive.
mkdir -p "$WS/.claude"
TS="$(date +%Y%m%d-%H%M%S)"
BK="$WS/.claude/.update-backup-$TS"

SHARED_DEFAULT="rules agents scripts skills CLAUDE.md HOW-TO-USE.md"
if [ -f "$TMP/x/shared-manifest.txt" ]; then
  SHARED="$(grep -vE '^[[:space:]]*(#|$)' "$TMP/x/shared-manifest.txt" | tr '\n' ' ')"
else
  SHARED="$SHARED_DEFAULT"
fi

# Pass each shared item as its own source (no trailing slash) so overwritten files keep
# their path prefix under the backup dir (e.g. rules/x.md -> $BK/rules/x.md). Skip items
# missing from the tarball instead of letting rsync abort under set -e.
SRCS=()
for item in $SHARED; do
  [ -e "$TMP/x/$item" ] && SRCS+=( "$TMP/x/$item" )
done
[ "${#SRCS[@]}" -gt 0 ] || { echo "error: nothing to sync — manifest empty or items missing from tarball." >&2; exit 1; }

echo "Updating $WS/.claude/ …"
RAW="$(rsync -ac --itemize-changes $DRY \
  --backup --backup-dir="$BK" \
  --exclude 'skills/_local/***' \
  "${SRCS[@]}" "$WS/.claude/")"
# Show only real content changes — new files (code has +++++++) and updated files (>f…) —
# labelled new / updated; drop directories and metadata-only churn (mtime/perms) that's just noise.
CHANGES="$(printf '%s\n' "$RAW" | grep -E '^[<>]f' \
  | sed -E 's/^[<>]f[^ ]*\+\+\+\+\+\+\+ /  new      /; s/^[<>]f[^ ]* /  updated  /' || true)"
NEW_N="$(printf '%s\n' "$CHANGES" | grep -c '^  new ' || true)"
UPD_N="$(printf '%s\n' "$CHANGES" | grep -c '^  updated ' || true)"
[ -n "$CHANGES" ] && printf '%s\n' "$CHANGES"

# 3. Activate the @-imported rules via a workspace-root CLAUDE.md symlink → .claude/CLAUDE.md.
#    Never clobber a real CLAUDE.md the workspace already has: only create/refresh the symlink
#    when there's no CLAUDE.md, or when it's already our symlink. If a real file is in the way,
#    leave it alone and tell the user how to wire the rules in themselves.
if [ -z "$DRY" ]; then
  if [ ! -e "$WS/CLAUDE.md" ] || [ -L "$WS/CLAUDE.md" ]; then
    ln -sfn .claude/CLAUDE.md "$WS/CLAUDE.md"
  else
    echo "note: $WS/CLAUDE.md already exists and is not our symlink — left untouched."
    echo "      To load the shared rules, add this import line to it:  @.claude/CLAUDE.md"
  fi
fi

# 4. Record the synced commit + the installed file list. The next run uses the commit to skip
#    the download when the remote hasn't moved, and the file list to detect locally-deleted
#    files (a removed skill) so it re-syncs to restore them instead of short-circuiting.
#    Real apply only, with a known SHA. Both files are per-machine state — gitignored and
#    excluded from contribute-skills.sh, so they never cross into the repo. The manifest lists
#    only repo-provided files (generated from the tarball), so rsync can always restore them.
if [ -z "$DRY" ] && [ -n "$REMOTE_SHA" ]; then
  printf '%s %s\n' "$REF" "$REMOTE_SHA" > "$STAMP"
  ( cd "$TMP/x" 2>/dev/null && for item in $SHARED; do
      [ -e "$item" ] && find "$item" -type f
    done ) 2>/dev/null | grep -v '^skills/_local/' > "$MANIFEST" || true
fi

echo
if [ -n "$DRY" ]; then
  if [ -n "$CHANGES" ]; then
    echo "[dry-run] would update .claude/ — $NEW_N new, $UPD_N updated. Nothing written."
  else
    echo "[dry-run] .claude/ is already current — nothing to do."
  fi
else
  if [ -n "$CHANGES" ]; then
    echo "✓ Updated .claude/ — $NEW_N new, $UPD_N updated."
    [ "$UPD_N" -gt 0 ] && echo "  Replaced files were backed up to: ${BK#$WS/}"
  else
    echo "✓ .claude/ is already current — nothing changed."
  fi
  echo "  Left untouched: your settings.local.json, .mcp.json, and skills/_local/."
  echo "  First time? Create .claude/settings.local.json and <workspace>/.mcp.json — ask the maintainer for the config."
fi
