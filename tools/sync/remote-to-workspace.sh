#!/usr/bin/env bash
#
# remote-to-workspace.sh — install or update remote shared content in workspace .claude/.
#
# ONE command, no clone, no GitHub auth (the repo is public — fetched over plain https).
# Run it the first time to install, re-run anytime to update. Idempotent.
#
# Quickest path — cd into the workspace, then run with NO arguments (workspace = current dir):
#   cd <your-workspace>
#   curl -fsSL https://raw.githubusercontent.com/trieuquanghuy/invocare-sdlc-skills/main/tools/sync/remote-to-workspace.sh | bash
#
# Or pass a path / flags explicitly (when piping, flags go after `-s --`):
#   ./tools/sync/remote-to-workspace.sh [path-to-workspace] [--dry-run] [--ref <branch|tag>] [--force]
#
#   --dry-run   show what would change; write nothing (recommended on first run)
#   --ref <x>   install a specific branch or CalVer tag (default: main)
#   --force     re-sync even when already up to date (skips the up-to-date short-circuit)
#
# Before downloading, it compares the repo's latest commit to the one it last synced
# (recorded in .claude/.skills-sync-state); on a match it prints "already up to date" and
# exits without downloading. Otherwise it makes .claude/ match the repo's shared set, backs
# up any file it overwrites, never deletes, and never touches your settings.local.json /
# .mcp.json / skills/_local/. On first install it also places the *.example templates beside
# their target config files so you can create your own settings.local.json + .mcp.json.
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

if [[ ! "$REF" =~ ^[A-Za-z0-9][A-Za-z0-9._/-]*$ ]]; then
  echo "error: invalid ref: use letters, numbers, dots, underscores, slashes, or hyphens." >&2
  exit 1
fi
case "/$REF/" in
  *"/../"*) echo "error: invalid ref: parent path segments are not allowed." >&2; exit 1 ;;
esac

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
MODE_LABEL="apply"
[ -n "$DRY" ] && MODE_LABEL="DRY-RUN (no changes written)"
echo "Mode:      $MODE_LABEL"
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
#    read by workspace-to-checkout.sh — one list, no "keep the two in sync" coupling). It is
#    an ALLOWLIST: only the listed top-level items are synced, so a new repo file is never
#    shipped to consumers until it's added to the manifest. A built-in default covers an
#    older tarball that predates the manifest.
#    -c (checksum) avoids spurious backups from the tarball's fresh extract mtimes;
#    --backup keeps every overwritten file; NO --delete, so personal skills survive.
[ -n "$DRY" ] || mkdir -p "$WS/.claude"
TS="$(date +%Y%m%d-%H%M%S)"
BK="$WS/.claude/.update-backup-$TS"

# Parse the shared manifest into an array so each entry is treated as a literal
# token — no word-splitting artefacts, no glob expansion, spaces in paths are safe.
SHARED_DEFAULT=(rules agents scripts skills HOW-TO-USE.md)
SHARED_ITEMS=()
if [ -f "$TMP/x/shared-manifest.txt" ]; then
  while IFS= read -r _line; do
    # strip leading/trailing whitespace, skip blank lines and comments
    _line="${_line#"${_line%%[! ]*}"}"
    _line="${_line%"${_line##*[! ]}"}"
    case "$_line" in ''|'#'*) continue ;; esac
    SHARED_ITEMS+=( "$_line" )
  done < "$TMP/x/shared-manifest.txt"
  [ "${#SHARED_ITEMS[@]}" -gt 0 ] || SHARED_ITEMS=( "${SHARED_DEFAULT[@]}" )
else
  SHARED_ITEMS=( "${SHARED_DEFAULT[@]}" )
fi

# Pass each shared item as its own source (no trailing slash) so overwritten files keep
# their path prefix under the backup dir (e.g. rules/x.md -> $BK/rules/x.md). Skip items
# missing from the tarball instead of letting rsync abort under set -e.
SRCS=()
for item in "${SHARED_ITEMS[@]}"; do
  [ -e "$TMP/x/$item" ] && SRCS+=( "$TMP/x/$item" )
done
[ "${#SRCS[@]}" -gt 0 ] || { echo "error: nothing to sync — manifest empty or items missing from tarball." >&2; exit 1; }
for source in "${SRCS[@]}"; do
  link="$(find "$source" -type l -print -quit)"
  [ -z "$link" ] || {
    echo "error: source symlink is not allowed: $link" >&2
    exit 1
  }
done
# Check for symlinks in hook sources (explicit mapping — layout differs from .claude/).
HOOK_SCRIPTS_SRC="$TMP/x/hooks/hooks"
HOOK_SETTINGS_SRC="$TMP/x/hooks/settings.json"
for _hsrc in "$HOOK_SCRIPTS_SRC" "$HOOK_SETTINGS_SRC"; do
  [ -e "$_hsrc" ] || continue
  _hlink="$(find "$_hsrc" -type l -print -quit)"
  [ -z "$_hlink" ] || {
    echo "error: source symlink is not allowed: $_hlink" >&2
    exit 1
  }
done

echo "Updating $WS/.claude/ …"
# In dry-run mode, GNU rsync (Linux) exits with code 3 when the destination
# directory does not yet exist.  Shadow nonexistent destinations to a temporary
# directory so --dry-run can still traverse and report what would change without
# touching the workspace.  When the real destination already exists we compare
# against it directly, keeping update-reporting accurate.
_dry_dest() {
  local real="$1" shadow_name="$2"
  if [ -n "$DRY" ] && [ ! -d "$real" ]; then
    local sd="$TMP/$shadow_name"
    mkdir -p "$sd"
    printf '%s' "$sd/"
  else
    printf '%s' "$real/"
  fi
}
CLAUDE_DEST="$(_dry_dest "$WS/.claude" "shadow-claude")"
RAW="$(rsync -ac --itemize-changes $DRY \
  --backup --backup-dir="$BK" \
  --exclude 'skills/_local/***' \
  "${SRCS[@]}" "$CLAUDE_DEST")"
# 2b. Install hooks with explicit mapping (hooks/ layout differs from .claude/ layout).
#     hooks/hooks/* → .claude/hooks/*  (scripts land flat, not nested)
#     hooks/settings.json → .claude/hooks/settings.json  (reference fragment; never settings.local.json)
[ -n "$DRY" ] || mkdir -p "$WS/.claude/hooks"
HOOK_RAW=""
if [ -d "$HOOK_SCRIPTS_SRC" ]; then
  HOOKS_DEST="$(_dry_dest "$WS/.claude/hooks" "shadow-hooks")"
  HOOK_RAW="$(rsync -ac --itemize-changes $DRY \
    --backup --backup-dir="$BK" \
    "$HOOK_SCRIPTS_SRC/" "$HOOKS_DEST")"
fi
HOOK_SETTINGS_RAW=""
if [ -f "$HOOK_SETTINGS_SRC" ]; then
  if [ -n "$DRY" ] && [ ! -d "$WS/.claude/hooks" ]; then
    # shadow-hooks may not have been created yet if HOOK_SCRIPTS_SRC was absent.
    mkdir -p "$TMP/shadow-hooks"
    _settings_shadow="$TMP/shadow-hooks/settings.json"
    HOOK_SETTINGS_RAW="$(rsync -ac --itemize-changes $DRY \
      --backup --backup-dir="$BK" \
      "$HOOK_SETTINGS_SRC" "$_settings_shadow")"
  else
    HOOK_SETTINGS_RAW="$(rsync -ac --itemize-changes $DRY \
      --backup --backup-dir="$BK" \
      "$HOOK_SETTINGS_SRC" "$WS/.claude/hooks/settings.json")"
  fi
fi
# Show only real content changes — new files (code has +++++++) and updated files (>f…) —
# labelled new / updated; drop directories and metadata-only churn (mtime/perms) that's just noise.
ALL_RAW="$RAW
$HOOK_RAW
$HOOK_SETTINGS_RAW"
CHANGES="$(printf '%s\n' "$ALL_RAW" | grep -E '^[<>]f' \
  | sed -E 's/^[<>]f[^ ]*\+\+\+\+\+\+\+ /  new      /; s/^[<>]f[^ ]* /  updated  /' || true)"
NEW_N="$(printf '%s\n' "$CHANGES" | grep -c '^  new ' || true)"
UPD_N="$(printf '%s\n' "$CHANGES" | grep -c '^  updated ' || true)"
[ -n "$CHANGES" ] && printf '%s\n' "$CHANGES"

# First install provides shape references without overwriting local examples on later runs.
install_example() {
  source_path="$1"
  destination="$2"
  [ -f "$source_path" ] && [ ! -e "$destination" ] || return 0
  if [ -n "$DRY" ]; then
    echo "  would create ${destination#"$WS/"}"
  else
    cp "$source_path" "$destination"
    echo "  created ${destination#"$WS/"}"
  fi
}
install_example "$TMP/x/settings.local.json.example" "$WS/.claude/settings.local.json.example"
install_example "$TMP/x/.mcp.json.example" "$WS/.mcp.json.example"

# 3. Maintain the workspace-ROOT CLAUDE.md (sibling of .claude/) so Claude Code loads the
#    shared rules natively — no symlink. We manage ONLY a marked block of @-imports built from
#    the installed rules/*.md; anything OUTSIDE the markers (your own content) is preserved.
#    Re-runs refresh the block, so new rules are picked up automatically.
if [ -z "$DRY" ]; then
  BEGIN='<!-- invocare-skills:begin (managed; do not edit inside) -->'
  LEGACY_BEGIN='<!-- invocare-skills:begin (managed by update-skills.sh — do not edit inside) -->'
  END='<!-- invocare-skills:end -->'
  ROOT_MD="$WS/CLAUDE.md"
  BLOCKFILE="$TMP/claude-block"
  MANAGED_BEGIN=""
  if [ ! -L "$ROOT_MD" ] && [ -f "$ROOT_MD" ]; then
    if grep -qF "$BEGIN" "$ROOT_MD" && grep -qF "$END" "$ROOT_MD"; then
      MANAGED_BEGIN="$BEGIN"
    elif grep -qF "$LEGACY_BEGIN" "$ROOT_MD" && grep -qF "$END" "$ROOT_MD"; then
      MANAGED_BEGIN="$LEGACY_BEGIN"
    fi
  fi
  {
    printf '%s\n' "$BEGIN"
    for f in "$WS"/.claude/rules/*.md; do
      [ -e "$f" ] && printf '@.claude/rules/%s\n' "$(basename "$f")"
    done
    printf '%s\n' "$END"
  } > "$BLOCKFILE"

  if [ -L "$ROOT_MD" ]; then
    # Legacy install left a symlink — replace it with a real managed file.
    rm -f "$ROOT_MD"; cp "$BLOCKFILE" "$ROOT_MD"
    echo "  CLAUDE.md: replaced the old symlink with a managed rules block"
  elif [ -n "$MANAGED_BEGIN" ]; then
    # Managed block already present — refresh it in place, keep everything else.
    awk -v bf="$BLOCKFILE" -v b="$MANAGED_BEGIN" -v e="$END" '
      $0==b && !replaced {
        while ((getline l < bf) > 0) print l
        close(bf)
        skip=1
        replaced=1
        next
      }
      skip && $0==e { skip=0; next }
      !skip { print }
    ' "$ROOT_MD" > "$ROOT_MD.tmp" && mv "$ROOT_MD.tmp" "$ROOT_MD"
    echo "  CLAUDE.md: refreshed the managed rules block"
  elif [ -f "$ROOT_MD" ]; then
    # Your own CLAUDE.md — prepend the block, keep all your content below it.
    { cat "$BLOCKFILE"; printf '\n'; cat "$ROOT_MD"; } > "$ROOT_MD.tmp" && mv "$ROOT_MD.tmp" "$ROOT_MD"
    echo "  CLAUDE.md: added the managed rules block above your existing content (kept intact)"
  else
    cp "$BLOCKFILE" "$ROOT_MD"
    echo "  CLAUDE.md: created at the workspace root with the shared rules"
  fi
fi

# 4. Record the synced commit + the installed file list. The next run uses the commit to skip
#    the download when the remote hasn't moved, and the file list to detect locally-deleted
#    files (a removed skill) so it re-syncs to restore them instead of short-circuiting.
#    Real apply only, with a known SHA. Both files are per-machine state — gitignored and
#    excluded from workspace-to-checkout.sh, so they never cross into the repo. The manifest lists
#    only repo-provided files (generated from the tarball), so rsync can always restore them.
if [ -z "$DRY" ] && [ -n "$REMOTE_SHA" ]; then
  printf '%s %s\n' "$REF" "$REMOTE_SHA" > "$STAMP"
  ( cd "$TMP/x" 2>/dev/null && for item in "${SHARED_ITEMS[@]}"; do
      [ -e "$item" ] && find "$item" -type f
    done ) 2>/dev/null | grep -v '^skills/_local/' > "$MANIFEST" || true
  # Append hook files (explicit mapping: hooks/hooks/* → hooks/*, hooks/settings.json → hooks/settings.json).
  if [ -d "$HOOK_SCRIPTS_SRC" ]; then
    ( cd "$HOOK_SCRIPTS_SRC" && find . -type f | sed 's|^\./|hooks/|' ) >> "$MANIFEST" 2>/dev/null || true
  fi
  [ -f "$HOOK_SETTINGS_SRC" ] && echo "hooks/settings.json" >> "$MANIFEST" || true
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
