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
# Requires: curl, tar, rsync, cksum (all preinstalled on macOS). gh is only a fallback.
set -euo pipefail

OWNER_REPO="trieuquanghuy/invocare-sdlc-skills"
REF="main"
DRY=""
WS=""
WS_SET=""
FORCE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY="--dry-run" ;;
    --ref)     shift; REF="${1:?--ref needs a value}" ;;
    --force)   FORCE=1 ;;
    -h|--help) sed -n '2,26p' "$0" 2>/dev/null | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*)        echo "unknown option: $1" >&2; exit 1 ;;
    *)         [ -z "$WS_SET" ] || {
                 echo "error: only one workspace path may be provided." >&2
                 exit 2
               }
               WS_SET=1
               WS="$1" ;;
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
if [ -z "$WS_SET" ]; then
  WS="$PWD"
elif [ -z "$WS" ]; then
  echo "error: workspace directory not found: empty path" >&2
  exit 1
fi
if ! WS_ABS="$(CDPATH= cd -- "$WS" >/dev/null 2>&1 && pwd -P)"; then
  echo "error: workspace directory not found: $WS" >&2; exit 1
fi
WS="$WS_ABS"
command -v rsync >/dev/null || { echo "error: rsync not found." >&2; exit 1; }
command -v tar   >/dev/null || { echo "error: tar not found." >&2; exit 1; }
command -v cksum >/dev/null 2>&1 && cksum </dev/null >/dev/null 2>&1 || {
  echo "error: cksum not found or not executable." >&2
  exit 1
}

CLAUDE_ROOT="$WS/.claude"
STAMP="$CLAUDE_ROOT/.skills-sync-state"
MANIFEST="$CLAUDE_ROOT/.skills-sync-manifest"
ROOT_MD="$WS/CLAUDE.md"

reject_destination_symlink() {
  [ ! -L "$1" ] || {
    echo "error: destination symlink is not allowed: $1" >&2
    exit 1
  }
}
has_symlink_component() {
  local root="$1" relative="$2" current part
  local parts=()
  IFS='/' read -r -a parts <<< "$relative"
  current="$root"
  for part in "${parts[@]}"; do
    current="$current/$part"
    [ ! -L "$current" ] || return 0
  done
  return 1
}
file_mode() {
  local path="$1" mode
  if mode="$(stat -c '%a' "$path" 2>/dev/null)" \
    && [[ "$mode" =~ ^[0-7]{1,4}$ ]]; then
    printf '%s\n' "$mode"
  elif mode="$(stat -f '%Lp' "$path" 2>/dev/null)" \
    && [[ "$mode" =~ ^[0-7]{1,4}$ ]]; then
    printf '%s\n' "$mode"
  else
    echo "error: cannot determine file mode: $path" >&2
    return 1
  fi
}

# These paths are used as directory roots or direct write targets. Following one
# would let an install modify files outside the selected workspace.
for destination in \
  "$CLAUDE_ROOT" \
  "$CLAUDE_ROOT/hooks" \
  "$CLAUDE_ROOT/hooks/settings.json" \
  "$STAMP" \
  "$MANIFEST" \
  "$CLAUDE_ROOT/settings.local.json.example" \
  "$WS/.mcp.json.example"
do
  reject_destination_symlink "$destination"
done
for destination in "$CLAUDE_ROOT" "$CLAUDE_ROOT/hooks"; do
  if [ -e "$destination" ] && [ ! -d "$destination" ]; then
    echo "error: destination must be a directory: $destination" >&2
    exit 1
  fi
done
for destination in \
  "$CLAUDE_ROOT/hooks/settings.json" \
  "$STAMP" \
  "$MANIFEST" \
  "$CLAUDE_ROOT/settings.local.json.example" \
  "$WS/.mcp.json.example"
do
  if [ -e "$destination" ] && [ ! -f "$destination" ]; then
    echo "error: destination must be a file: $destination" >&2
    exit 1
  fi
done
if [ -e "$ROOT_MD" ] && [ ! -f "$ROOT_MD" ] && [ ! -L "$ROOT_MD" ]; then
  echo "error: CLAUDE.md must be a file or symlink: $ROOT_MD" >&2
  exit 1
fi
if [ ! -L "$ROOT_MD" ] && [ -f "$ROOT_MD" ] && [ ! -r "$ROOT_MD" ]; then
  echo "error: CLAUDE.md is not readable: $ROOT_MD" >&2
  exit 1
fi

TMP="$(mktemp -d)"
ROOT_MD_TMP=""
MANIFEST_TMP=""
STAMP_TMP=""
BK=""
BACKUP_OCCURRED=""
cleanup() {
  status=$?
  trap - EXIT
  set +e
  [ -z "$ROOT_MD_TMP" ] || rm -f "$ROOT_MD_TMP"
  [ -z "$MANIFEST_TMP" ] || rm -f "$MANIFEST_TMP"
  [ -z "$STAMP_TMP" ] || rm -f "$STAMP_TMP"
  [ -z "$BK" ] || rmdir "$BK" 2>/dev/null || true
  rm -rf "$TMP"
  exit "$status"
}
trap cleanup EXIT

BEGIN='<!-- invocare-skills:begin (managed; do not edit inside) -->'
LEGACY_BEGIN='<!-- invocare-skills:begin (managed by update-skills.sh — do not edit inside) -->'
END='<!-- invocare-skills:end -->'
root_claude_is_current() {
  local names="$TMP/current-rule-names"
  local expected="$TMP/current-claude-block"
  local actual="$TMP/current-claude-managed"
  local rule
  [ -f "$ROOT_MD" ] && [ ! -L "$ROOT_MD" ] || return 1

  : > "$names"
  if [ -d "$CLAUDE_ROOT/rules" ] && [ ! -L "$CLAUDE_ROOT/rules" ]; then
    for rule in "$CLAUDE_ROOT"/rules/*.md; do
      [ -e "$rule" ] && printf '%s\n' "$(basename "$rule")" >> "$names"
    done
  fi
  {
    printf '%s\n' "$BEGIN"
    LC_ALL=C sort -u "$names" | while IFS= read -r rule_name; do
      [ -n "$rule_name" ] && printf '@.claude/rules/%s\n' "$rule_name"
    done
    printf '%s\n' "$END"
  } > "$expected"
  awk -v b="$BEGIN" -v lb="$LEGACY_BEGIN" -v e="$END" '
    $0 == b || $0 == lb {
      begin_count++
      if ($0 != b || begin_count != 1 || end_count != 0) invalid=1
      if (!invalid) { capture=1; print }
      next
    }
    $0 == e {
      end_count++
      if (begin_count != 1 || end_count != 1 || !capture) invalid=1
      if (capture) print
      capture=0
      next
    }
    capture { print }
    END {
      if (invalid || begin_count != 1 || end_count != 1 || capture) exit 1
    }
  ' "$ROOT_MD" > "$actual" || return 1
  cmp -s "$expected" "$actual"
}

echo "Repo:      $OWNER_REPO @ $REF (public)"
echo "Workspace: $WS"
MODE_LABEL="apply"
[ -n "$DRY" ] && MODE_LABEL="DRY-RUN (no changes written)"
echo "Mode:      $MODE_LABEL"
echo

# 0. Up-to-date check. Resolve the ref's latest commit SHA (cheap — no tarball) and compare
#    it to the SHA recorded after the last sync. On a match (and no --force) skip the whole
#    download. SHA-fetch failure is non-fatal: fall through to the normal download path.
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
  STAMP_REF=""
  STAMP_SHA=""
  STAMP_MANIFEST_CKSUM=""
  STAMP_MANIFEST_BYTES=""
  read -r STAMP_REF STAMP_SHA STAMP_MANIFEST_CKSUM STAMP_MANIFEST_BYTES _ \
    < "$STAMP" 2>/dev/null || true
  if [ "${STAMP_REF:-}" = "$REF" ] && [ "${STAMP_SHA:-}" = "$REMOTE_SHA" ]; then
    MANIFEST_SIGNATURE="$(cksum < "$MANIFEST" 2>/dev/null || true)"
    MANIFEST_CKSUM=""
    MANIFEST_BYTES=""
    read -r MANIFEST_CKSUM MANIFEST_BYTES _ <<< "$MANIFEST_SIGNATURE" || true
    if [ ! -s "$MANIFEST" ] \
      || [ -z "$STAMP_MANIFEST_CKSUM" ] \
      || [ "$STAMP_MANIFEST_CKSUM" != "$MANIFEST_CKSUM" ] \
      || [ "$STAMP_MANIFEST_BYTES" != "$MANIFEST_BYTES" ]; then
      echo "Up to date with $REF @ ${REMOTE_SHA:0:7}, but local sync tracking is incomplete or changed — re-syncing to repair it."
    else
      # Remote unchanged. Only skip the download if the install is still COMPLETE — every file
      # recorded at last sync still exists. A deleted skill/file is local drift, so fall through
      # and re-sync to restore it.
      MISSING=0
      while IFS= read -r rel; do
        [ -n "$rel" ] || continue
        managed_path="$CLAUDE_ROOT/$rel"
        if has_symlink_component "$CLAUDE_ROOT" "$rel" \
          || [ ! -f "$managed_path" ]; then
          MISSING=$((MISSING + 1))
        fi
      done < "$MANIFEST"
      ROOT_MD_STALE=""
      if [ ! -f "$ROOT_MD" ] || [ -L "$ROOT_MD" ]; then
        MISSING=$((MISSING + 1))
      elif ! root_claude_is_current; then
        ROOT_MD_STALE=1
      fi
      if [ "$MISSING" -eq 0 ] && [ -z "$ROOT_MD_STALE" ]; then
        echo "Already up to date: $REF @ ${REMOTE_SHA:0:7} — last synced from this commit."
        echo "  Use --force to re-sync anyway (e.g. to restore locally-changed files)."
        exit 0
      fi
      if [ "$MISSING" -gt 0 ]; then
        echo "Up to date with $REF @ ${REMOTE_SHA:0:7}, but $MISSING managed file(s) missing locally — re-syncing to restore them."
      else
        echo "Up to date with $REF @ ${REMOTE_SHA:0:7}, but CLAUDE.md needs refresh — re-syncing to repair it."
      fi
    fi
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
#    -c compares content and --no-times ignores the tarball's fresh extract mtimes;
#    --backup keeps every overwritten file; NO --delete, so personal skills survive.
# Parse the shared manifest into an array so each entry is treated as a literal
# token — no word-splitting artefacts, no glob expansion, spaces in paths are safe.
SHARED_DEFAULT=(rules agents scripts skills HOW-TO-USE.md)
SHARED_ITEMS=()
SHARED_MANIFEST="$TMP/x/shared-manifest.txt"
if [ -L "$SHARED_MANIFEST" ]; then
  echo "error: source symlink is not allowed: $SHARED_MANIFEST" >&2
  exit 1
fi
if [ -e "$SHARED_MANIFEST" ] && [ ! -f "$SHARED_MANIFEST" ]; then
  echo "error: shared manifest must be a file: $SHARED_MANIFEST" >&2
  exit 1
fi
if [ -f "$SHARED_MANIFEST" ]; then
  _line=""
  while IFS= read -r _line || [ -n "$_line" ]; do
    # strip leading/trailing whitespace, skip blank lines and comments
    _line="${_line#"${_line%%[! ]*}"}"
    _line="${_line%"${_line##*[! ]}"}"
    case "$_line" in ''|'#'*) continue ;; esac
    case "$_line" in
      .|..|-*|*/*)
        echo "error: shared manifest entry must be a top-level item: $_line" >&2
        exit 1
        ;;
    esac
    _normalized="$(printf '%s' "$_line" | LC_ALL=C tr '[:upper:]' '[:lower:]')"
    case "$_normalized" in
      settings.local.json|settings.local.json.example|.mcp.json|.mcp.json.example|\
      .skills-sync-state|.skills-sync-manifest|.update-backup-*|claude.md|\
      shared-manifest.txt|hooks)
        echo "error: shared manifest contains protected item: $_line" >&2
        exit 1
        ;;
    esac
    case "$_normalized" in
      rules|agents|scripts|skills)
        if [ "$_line" != "$_normalized" ]; then
          echo "error: shared manifest item must use canonical case: $_line" >&2
          exit 1
        fi
        ;;
      how-to-use.md)
        if [ "$_line" != "HOW-TO-USE.md" ]; then
          echo "error: shared manifest item must use canonical case: $_line" >&2
          exit 1
        fi
        ;;
    esac
    SHARED_ITEMS+=( "$_line" )
  done < "$SHARED_MANIFEST"
  [ "${#SHARED_ITEMS[@]}" -gt 0 ] || {
    echo "error: shared manifest is empty: $SHARED_MANIFEST" >&2
    exit 1
  }
else
  SHARED_ITEMS=( "${SHARED_DEFAULT[@]}" )
fi

# Pass each shared item as its own source (no trailing slash) so overwritten files keep
# their path prefix under the backup dir (e.g. rules/x.md -> $BK/rules/x.md). Skip items
# missing from the tarball instead of letting rsync abort under set -e.
SRCS=()
for item in "${SHARED_ITEMS[@]}"; do
  candidate="$TMP/x/$item"
  if [ -L "$candidate" ]; then
    echo "error: source symlink is not allowed: $candidate" >&2
    exit 1
  fi
  case "$item" in
    rules|agents|scripts|skills)
      if [ -e "$candidate" ] && [ ! -d "$candidate" ]; then
        echo "error: $item source must be a directory: $candidate" >&2
        exit 1
      fi
      ;;
    HOW-TO-USE.md)
      if [ -e "$candidate" ] && [ ! -f "$candidate" ]; then
        echo "error: HOW-TO-USE.md source must be a file: $candidate" >&2
        exit 1
      fi
      ;;
  esac
  [ -e "$candidate" ] && SRCS+=( "$candidate" )
done
[ "${#SRCS[@]}" -gt 0 ] || { echo "error: nothing to sync — manifest empty or items missing from tarball." >&2; exit 1; }
if [ -d "$TMP/x/skills" ]; then
  while IFS= read -r skill_path; do
    [ "$skill_path" != "$TMP/x/skills" ] || continue
    skill_relative="${skill_path#"$TMP/x/skills/"}"
    skill_root="${skill_relative%%/*}"
    normalized_skill_root="$(
      printf '%s' "$skill_root" | LC_ALL=C tr '[:upper:]' '[:lower:]'
    )"
    if [ "$normalized_skill_root" = "_local" ]; then
      echo "error: source contains reserved local skill directory: $skill_path" >&2
      exit 1
    fi
  done < <(find "$TMP/x/skills" -print)
fi
for source in "${SRCS[@]}"; do
  link="$(find "$source" -type l -print -quit)"
  [ -z "$link" ] || {
    echo "error: source symlink is not allowed: $link" >&2
    exit 1
  }
done
# Check explicitly mapped sources that sit outside the shared manifest.
HOOK_SCRIPTS_SRC="$TMP/x/hooks/hooks"
HOOK_SETTINGS_SRC="$TMP/x/hooks/settings.json"
for _mapped_src in \
  "$TMP/x/hooks" \
  "$TMP/x/settings.local.json.example" \
  "$TMP/x/.mcp.json.example"
do
  if [ ! -e "$_mapped_src" ] && [ ! -L "$_mapped_src" ]; then
    continue
  fi
  _mapped_link="$(find "$_mapped_src" -type l -print -quit)"
  [ -z "$_mapped_link" ] || {
    echo "error: source symlink is not allowed: $_mapped_link" >&2
    exit 1
  }
done
if [ -e "$HOOK_SCRIPTS_SRC/settings.json" ] && [ -e "$HOOK_SETTINGS_SRC" ]; then
  echo "error: hook source mapping collision: hooks/hooks/settings.json and hooks/settings.json" >&2
  exit 1
fi

TYPE_CONFLICT_N=0
if [ -n "$DRY" ]; then
  BK="$TMP/update-backup"
  SYNC_ROOT="$TMP/shadow-claude"
  mkdir -p "$BK" "$SYNC_ROOT"
  DRY_CONFLICTS=()

  is_under_dry_conflict() {
    local relative="$1" conflict
    [ "${#DRY_CONFLICTS[@]}" -gt 0 ] || return 1
    for conflict in "${DRY_CONFLICTS[@]}"; do
      case "$relative" in
        "$conflict"|"$conflict"/*) return 0 ;;
      esac
    done
    return 1
  }

  prepare_dry_path() {
    local source_path="$1" relative="$2"
    local destination_path="$CLAUDE_ROOT/$relative"
    local shadow_path="$SYNC_ROOT/$relative"
    local conflict=""

    is_under_dry_conflict "$relative" && return 0
    if [ -L "$destination_path" ]; then
      conflict=1
    elif [ -e "$destination_path" ]; then
      if [ -d "$source_path" ] && [ ! -d "$destination_path" ]; then
        conflict=1
      elif [ -f "$source_path" ] && [ ! -f "$destination_path" ]; then
        conflict=1
      fi
    fi
    if [ -n "$conflict" ]; then
      DRY_CONFLICTS+=( "$relative" )
      TYPE_CONFLICT_N=$((TYPE_CONFLICT_N + 1))
      echo "  would back up type conflict: $relative"
      return 0
    fi

    if [ -d "$source_path" ]; then
      if [ -d "$destination_path" ]; then
        mkdir -p "$shadow_path"
        chmod "$(file_mode "$destination_path")" "$shadow_path"
      fi
    elif [ -f "$source_path" ] && [ -f "$destination_path" ]; then
      mkdir -p "$(dirname "$shadow_path")"
      if ! cp -p "$destination_path" "$shadow_path" 2>/dev/null; then
        rm -f "$shadow_path"
        printf 'invocare-unreadable:%s\n' "$relative" > "$shadow_path"
        if cmp -s "$source_path" "$shadow_path"; then
          printf 'x' >> "$shadow_path"
        fi
        echo "  would update unreadable file: $relative"
      fi
    fi
    return 0
  }

  for source in "${SRCS[@]}"; do
    while IFS= read -r source_path; do
      relative="${source_path#"$TMP/x/"}"
      prepare_dry_path "$source_path" "$relative"
    done < <(find "$source" -print)
  done
  if [ -d "$HOOK_SCRIPTS_SRC" ]; then
    while IFS= read -r source_path; do
      [ "$source_path" != "$HOOK_SCRIPTS_SRC" ] || continue
      relative="hooks/${source_path#"$HOOK_SCRIPTS_SRC"/}"
      prepare_dry_path "$source_path" "$relative"
    done < <(find "$HOOK_SCRIPTS_SRC" -print)
  fi
  if [ -f "$HOOK_SETTINGS_SRC" ]; then
    prepare_dry_path "$HOOK_SETTINGS_SRC" "hooks/settings.json"
  fi
else
  mkdir -p "$CLAUDE_ROOT"
  TS="$(date +%Y%m%d-%H%M%S)"
  BK="$(mktemp -d "$CLAUDE_ROOT/.update-backup-$TS.XXXXXX")"
  SYNC_ROOT="$CLAUDE_ROOT"

  backup_type_conflict() {
    local source_path="$1" relative="$2"
    local destination_path="$SYNC_ROOT/$relative"
    local backup_path="$BK/$relative"
    local conflict=""

    if [ -L "$destination_path" ]; then
      conflict=1
    elif [ -e "$destination_path" ]; then
      if [ -d "$source_path" ] && [ ! -d "$destination_path" ]; then
        conflict=1
      elif [ -f "$source_path" ] && [ ! -f "$destination_path" ]; then
        conflict=1
      fi
    fi
    [ -n "$conflict" ] || return 0

    mkdir -p "$(dirname "$backup_path")"
    mv "$destination_path" "$backup_path"
    BACKUP_OCCURRED=1
    TYPE_CONFLICT_N=$((TYPE_CONFLICT_N + 1))
    echo "  backed up type conflict: $relative"
  }

  for source in "${SRCS[@]}"; do
    while IFS= read -r source_path; do
      relative="${source_path#"$TMP/x/"}"
      backup_type_conflict "$source_path" "$relative"
    done < <(find "$source" -print)
  done
  if [ -d "$HOOK_SCRIPTS_SRC" ]; then
    while IFS= read -r source_path; do
      [ "$source_path" != "$HOOK_SCRIPTS_SRC" ] || continue
      relative="hooks/${source_path#"$HOOK_SCRIPTS_SRC"/}"
      backup_type_conflict "$source_path" "$relative"
    done < <(find "$HOOK_SCRIPTS_SRC" -print)
  fi
fi
echo "Updating $WS/.claude/ …"
CLAUDE_DEST="$SYNC_ROOT/"
RAW="$(rsync -ac --no-times --itemize-changes $DRY \
  --backup --backup-dir="$BK" \
  --exclude 'skills/_local/***' \
  "${SRCS[@]}" "$CLAUDE_DEST")"
# 2b. Install hooks with explicit mapping (hooks/ layout differs from .claude/ layout).
#     hooks/hooks/* → .claude/hooks/*  (scripts land flat, not nested)
#     hooks/settings.json → .claude/hooks/settings.json  (reference fragment; never settings.local.json)
mkdir -p "$SYNC_ROOT/hooks"
HOOK_RAW=""
if [ -d "$HOOK_SCRIPTS_SRC" ]; then
  HOOKS_DEST="$SYNC_ROOT/hooks/"
  HOOK_RAW="$(rsync -ac --no-times --itemize-changes $DRY \
    --backup --backup-dir="$BK/hooks" \
    "$HOOK_SCRIPTS_SRC/" "$HOOKS_DEST")"
fi
HOOK_SETTINGS_RAW=""
if [ -f "$HOOK_SETTINGS_SRC" ]; then
  HOOK_SETTINGS_RAW="$(rsync -ac --no-times --itemize-changes $DRY \
    --backup --backup-dir="$BK/hooks" \
    "$HOOK_SETTINGS_SRC" "$SYNC_ROOT/hooks/")"
fi
# Show only real content changes — new files (code has +++++++) and updated files (>f…) —
# labelled new / updated; drop directories and metadata-only churn (mtime/perms) that's just noise.
ALL_RAW="$RAW
$HOOK_RAW
$HOOK_SETTINGS_RAW"
CONTENT_CHANGES="$(printf '%s\n' "$ALL_RAW" | grep -E '^[<>]f' \
  | sed -E 's/^[<>]f[^ ]*\+\+\+\+\+\+\+ /  new      /; s/^[<>]f[^ ]* /  updated  /' || true)"
METADATA_CHANGES="$(printf '%s\n' "$ALL_RAW" | grep -E '^\.[fd][^ ]*[poguax][^ ]* ' \
  | sed -E 's/^\.[^ ]* /  metadata /' || true)"
CHANGES="$(printf '%s\n%s\n' "$CONTENT_CHANGES" "$METADATA_CHANGES" | sed '/^$/d')"
NEW_N="$(printf '%s\n' "$CHANGES" | grep -c '^  new ' || true)"
UPD_N="$(printf '%s\n' "$CHANGES" | grep -c '^  updated ' || true)"
META_N="$(printf '%s\n' "$CHANGES" | grep -c '^  metadata ' || true)"
[ -n "$CHANGES" ] && printf '%s\n' "$CHANGES"

# First install provides shape references without overwriting local examples on later runs.
EXAMPLE_N=0
install_example() {
  local source_path="$1"
  local destination="$2"
  [ -f "$source_path" ] && [ ! -e "$destination" ] || return 0
  EXAMPLE_N=$((EXAMPLE_N + 1))
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
detect_managed_begin() {
    local current_begin="$1" legacy_begin="$2" end="$3" path="$4"
    awk -v cb="$current_begin" -v lb="$legacy_begin" -v e="$end" '
      $0 == cb || $0 == lb {
        begin_count++
        if (begin_count == 1 && end_count == 0) {
          begin=$0
        } else {
          invalid=1
        }
        next
      }
      $0 == e {
        end_count++
        if (begin_count != 1 || end_count != 1) invalid=1
        next
      }
      END {
        if (!invalid && begin_count == 1 && end_count == 1) {
          print begin
          exit 0
        }
        exit 1
      }
    ' "$path"
  }
  detect_leading_managed_begin() {
    local current_begin="$1" legacy_begin="$2" end="$3" path="$4"
    awk -v cb="$current_begin" -v lb="$legacy_begin" -v e="$end" '
      NR == 1 {
        if ($0 != cb && $0 != lb) { invalid=1; exit }
        begin=$0
        next
      }
      $0 == cb || $0 == lb { invalid=1; exit }
      $0 == e { found=1; exit }
      END {
        if (!invalid && found) {
          print begin
          exit 0
        }
        exit 1
      }
    ' "$path"
  }
  has_managed_marker() {
    local current_begin="$1" legacy_begin="$2" end="$3" path="$4"
    awk -v cb="$current_begin" -v lb="$legacy_begin" -v e="$end" '
      $0 == cb || $0 == lb || $0 == e { found=1; exit }
      END { exit(found ? 0 : 1) }
    ' "$path"
  }
  append_rule_names() {
    local rules_dir="$1" rule
    [ -d "$rules_dir" ] && [ ! -L "$rules_dir" ] || return 0
    for rule in "$rules_dir"/*.md; do
      [ -e "$rule" ] && printf '%s\n' "$(basename "$rule")" >> "$RULE_NAMES"
    done
    return 0
  }

  BLOCKFILE="$TMP/claude-block"
  RULE_NAMES="$TMP/claude-rule-names"
  : > "$RULE_NAMES"
  append_rule_names "$CLAUDE_ROOT/rules"
  if [ -n "$DRY" ]; then
    for source in "${SRCS[@]}"; do
      [ "$source" != "$TMP/x/rules" ] || append_rule_names "$source"
    done
  fi
  {
    printf '%s\n' "$BEGIN"
    LC_ALL=C sort -u "$RULE_NAMES" | while IFS= read -r rule_name; do
      [ -n "$rule_name" ] && printf '@.claude/rules/%s\n' "$rule_name"
    done
    printf '%s\n' "$END"
  } > "$BLOCKFILE"

  MANAGED_BEGIN=""
  MARKER_STATE="absent"
  if [ ! -L "$ROOT_MD" ] && [ -f "$ROOT_MD" ]; then
    if detected_begin="$(detect_managed_begin "$BEGIN" "$LEGACY_BEGIN" "$END" "$ROOT_MD")"; then
      MANAGED_BEGIN="$detected_begin"
      MARKER_STATE="valid"
    elif detected_begin="$(detect_leading_managed_begin "$BEGIN" "$LEGACY_BEGIN" "$END" "$ROOT_MD")"; then
      MANAGED_BEGIN="$detected_begin"
      MARKER_STATE="managed-prefix"
    elif has_managed_marker "$BEGIN" "$LEGACY_BEGIN" "$END" "$ROOT_MD"; then
      MARKER_STATE="malformed"
    fi
  fi

  if [ -n "$DRY" ]; then
    ROOT_MD_TMP="$TMP/CLAUDE.md.preview"
  else
    ROOT_MD_TMP="$(mktemp "$WS/.CLAUDE.md.tmp.XXXXXX")"
  fi
  ROOT_MD_WAS_SYMLINK=""
  if [ -L "$ROOT_MD" ]; then
    # Legacy install left a symlink — replace it with a real managed file.
    cat "$BLOCKFILE" > "$ROOT_MD_TMP"
    ROOT_MD_MODE_SOURCE="$BLOCKFILE"
    ROOT_MD_WAS_SYMLINK=1
    ROOT_MD_MESSAGE="replaced the old symlink with a managed rules block"
    ROOT_MD_PREVIEW="would replace CLAUDE.md symlink with a managed file"
  elif [ -n "$MANAGED_BEGIN" ]; then
    # Managed block already present — refresh it in place, keep everything else.
    ROOT_MD_MODE_SOURCE="$ROOT_MD"
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
    ' "$ROOT_MD" > "$ROOT_MD_TMP"
    ROOT_MD_MESSAGE="refreshed the managed rules block"
    ROOT_MD_PREVIEW="would refresh CLAUDE.md managed rules block"
  elif [ -f "$ROOT_MD" ]; then
    # Your own CLAUDE.md — prepend the block, keep all your content below it.
    ROOT_MD_MODE_SOURCE="$ROOT_MD"
    { cat "$BLOCKFILE"; printf '\n'; cat "$ROOT_MD"; } > "$ROOT_MD_TMP"
    if [ "$MARKER_STATE" = "malformed" ]; then
      ROOT_MD_MESSAGE="preserved malformed markers and added a managed rules block"
      ROOT_MD_PREVIEW="would preserve malformed markers and add a managed CLAUDE.md rules block"
    else
      ROOT_MD_MESSAGE="added the managed rules block above your existing content (kept intact)"
      ROOT_MD_PREVIEW="would add a managed rules block to CLAUDE.md"
    fi
  else
    cat "$BLOCKFILE" > "$ROOT_MD_TMP"
    ROOT_MD_MODE_SOURCE="$BLOCKFILE"
    ROOT_MD_MESSAGE="created at the workspace root with the shared rules"
    ROOT_MD_PREVIEW="would create CLAUDE.md with the shared rules"
  fi

  ROOT_MD_CHANGE=1
  if [ -f "$ROOT_MD" ] && [ ! -L "$ROOT_MD" ] && cmp -s "$ROOT_MD_TMP" "$ROOT_MD"; then
    ROOT_MD_CHANGE=""
  fi
  if [ -n "$DRY" ]; then
    [ -z "$ROOT_MD_CHANGE" ] || echo "  $ROOT_MD_PREVIEW"
    rm -f "$ROOT_MD_TMP"
    ROOT_MD_TMP=""
  elif [ -n "$ROOT_MD_CHANGE" ]; then
    ROOT_MD_MODE="$(file_mode "$ROOT_MD_MODE_SOURCE")"
    chmod "$ROOT_MD_MODE" "$ROOT_MD_TMP"
    [ -z "$ROOT_MD_WAS_SYMLINK" ] || rm -f "$ROOT_MD"
    mv -f "$ROOT_MD_TMP" "$ROOT_MD"
    ROOT_MD_TMP=""
    echo "  CLAUDE.md: $ROOT_MD_MESSAGE"
  else
    rm -f "$ROOT_MD_TMP"
    ROOT_MD_TMP=""
  fi

# 4. Record the synced commit + the installed file list. The next run uses the commit to skip
#    the download when the remote hasn't moved, and the file list to detect locally-deleted
#    files (a removed skill) so it re-syncs to restore them instead of short-circuiting.
#    Real apply only, with a known SHA. Both files are per-machine state — gitignored and
#    excluded from workspace-to-checkout.sh, so they never cross into the repo. The manifest lists
#    only repo-provided files (generated from the tarball), so rsync can always restore them.
if [ -z "$DRY" ] && [ -n "$REMOTE_SHA" ]; then
  MANIFEST_TMP="$(mktemp "$CLAUDE_ROOT/.skills-sync-manifest.tmp.XXXXXX")"
  STAMP_TMP="$(mktemp "$CLAUDE_ROOT/.skills-sync-state.tmp.XXXXXX")"
  (
    cd "$TMP/x"
    for item in "${SHARED_ITEMS[@]}"; do
      if [ -e "$item" ]; then
        find "$item" -type f
      fi
    done
  ) | awk '$0 !~ /^skills\/_local\//' > "$MANIFEST_TMP"
  # Append hook files (explicit mapping: hooks/hooks/* → hooks/*, hooks/settings.json → hooks/settings.json).
  if [ -d "$HOOK_SCRIPTS_SRC" ]; then
    (
      cd "$HOOK_SCRIPTS_SRC"
      find . -type f | sed 's|^\./|hooks/|'
    ) >> "$MANIFEST_TMP"
  fi
  [ -f "$HOOK_SETTINGS_SRC" ] && echo "hooks/settings.json" >> "$MANIFEST_TMP"
  read -r MANIFEST_CKSUM MANIFEST_BYTES _ < <(cksum < "$MANIFEST_TMP")
  printf '%s %s %s %s\n' \
    "$REF" "$REMOTE_SHA" "$MANIFEST_CKSUM" "$MANIFEST_BYTES" > "$STAMP_TMP"
  mv -f "$MANIFEST_TMP" "$MANIFEST"
  MANIFEST_TMP=""
  mv -f "$STAMP_TMP" "$STAMP"
  STAMP_TMP=""
fi

echo
if [ -n "$DRY" ]; then
  ROOT_MD_SUMMARY=""
  [ -z "$ROOT_MD_CHANGE" ] || ROOT_MD_SUMMARY="; CLAUDE.md would change"
  EXAMPLE_SUMMARY=""
  [ "$EXAMPLE_N" -eq 0 ] || EXAMPLE_SUMMARY="; $EXAMPLE_N configuration example(s) would be created"
  CONFLICT_SUMMARY=""
  [ "$TYPE_CONFLICT_N" -eq 0 ] || CONFLICT_SUMMARY="; $TYPE_CONFLICT_N type conflict(s) would be backed up"
  if [ -n "$CHANGES" ]; then
    CHANGE_SUMMARY="$NEW_N new, $UPD_N updated"
    [ "$META_N" -eq 0 ] || CHANGE_SUMMARY="$CHANGE_SUMMARY, $META_N metadata"
    echo "[dry-run] would update .claude/ — $CHANGE_SUMMARY$ROOT_MD_SUMMARY$EXAMPLE_SUMMARY$CONFLICT_SUMMARY. Nothing written."
  elif [ -n "$ROOT_MD_CHANGE" ] || [ "$EXAMPLE_N" -gt 0 ] || [ "$TYPE_CONFLICT_N" -gt 0 ]; then
    echo "[dry-run] .claude/ shared files are current$ROOT_MD_SUMMARY$EXAMPLE_SUMMARY$CONFLICT_SUMMARY. Nothing written."
  else
    echo "[dry-run] .claude/ is already current — nothing to do."
  fi
else
  ROOT_MD_APPLY_SUMMARY=""
  [ -z "$ROOT_MD_CHANGE" ] || ROOT_MD_APPLY_SUMMARY="; CLAUDE.md updated"
  EXAMPLE_APPLY_SUMMARY=""
  [ "$EXAMPLE_N" -eq 0 ] || EXAMPLE_APPLY_SUMMARY="; $EXAMPLE_N configuration example(s) created"
  CONFLICT_APPLY_SUMMARY=""
  [ "$TYPE_CONFLICT_N" -eq 0 ] || CONFLICT_APPLY_SUMMARY="; $TYPE_CONFLICT_N type conflict(s) backed up"
  if [ -n "$CHANGES" ]; then
    CHANGE_SUMMARY="$NEW_N new, $UPD_N updated"
    [ "$META_N" -eq 0 ] || CHANGE_SUMMARY="$CHANGE_SUMMARY, $META_N metadata"
    echo "✓ Updated .claude/ — $CHANGE_SUMMARY$ROOT_MD_APPLY_SUMMARY$EXAMPLE_APPLY_SUMMARY$CONFLICT_APPLY_SUMMARY."
  elif [ -n "$ROOT_MD_CHANGE" ] || [ "$EXAMPLE_N" -gt 0 ] || [ "$TYPE_CONFLICT_N" -gt 0 ]; then
    echo "✓ Shared .claude/ files are current$ROOT_MD_APPLY_SUMMARY$EXAMPLE_APPLY_SUMMARY$CONFLICT_APPLY_SUMMARY."
  else
    echo "✓ .claude/ is already current — nothing changed."
  fi
  if [ "$UPD_N" -gt 0 ] || [ -n "$BACKUP_OCCURRED" ]; then
    echo "  Replaced files were backed up to: ${BK#"$WS/"}"
  fi
  echo "  Left untouched: your settings.local.json, .mcp.json, and skills/_local/."
  echo "  First time? Create .claude/settings.local.json and <workspace>/.mcp.json — ask the maintainer for the config."
fi
