#!/bin/bash
# SDLC gate: enforce code-lesson MCP pre-implementation gate at the harness layer.
# Reads Claude Code hook JSON from stdin. Three modes:
#   check   PreToolUse on code edits — block unless every lesson stage completed this task
#   set     PostToolUse on *         — record completed code-lesson stages
#   clear   UserPromptSubmit         — clear the sentinel so each new user prompt re-arms the gate
#
# See .claude/rules/sdlc-gates.md for the SDLC stages this enforces.

set -u

MODE="${1:-}"
INPUT=$(cat)
SID=$(printf '%s' "$INPUT" | jq -r '.session_id // ""')
WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"

emit_deny() {
  cat <<'JSON'
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "SDLC GATE (.claude/rules/sdlc-gates.md Stage S1): complete the code-lesson high and medium skims, then fetch relevant lesson IDs before editing code."
  }
}
JSON
}

if [ -n "$SID" ]; then
  STATE_DIR="${TMPDIR:-/tmp}/claude-sdlc-gate"
  STATE_KEY=$(printf '%s' "$SID" | shasum -a 256 | awk '{print $1}')
  HIGH_FLAG="$STATE_DIR/${STATE_KEY}.high"
  MEDIUM_FLAG="$STATE_DIR/${STATE_KEY}.medium"
  FETCH_FLAG="$STATE_DIR/${STATE_KEY}.fetch"
fi

state_dir_is_safe() {
  [ -d "$STATE_DIR" ] && [ ! -L "$STATE_DIR" ] || return 1
  if stat -f '%u' "$STATE_DIR" >/dev/null 2>&1; then
    STATE_OWNER=$(stat -f '%u' "$STATE_DIR")
  else
    STATE_OWNER=$(stat -c '%u' "$STATE_DIR") || return 1
  fi
  [ "$STATE_OWNER" = "$(id -u)" ]
}

prepare_state_dir() {
  [ ! -L "$STATE_DIR" ] || return 1
  umask 077
  mkdir -p "$STATE_DIR" || return 1
  state_dir_is_safe || return 1
  chmod 700 "$STATE_DIR"
}

create_flag() {
  FLAG_PATH="$1"
  [ ! -L "$FLAG_PATH" ] || return 1
  TEMP_FLAG=$(mktemp "$STATE_DIR/.flag.XXXXXX") || return 1
  chmod 600 "$TEMP_FLAG"
  mv -f "$TEMP_FLAG" "$FLAG_PATH"
}

valid_flag() {
  [ -f "$1" ] && [ ! -L "$1" ]
}

canonicalize_target() {
  TARGET_PATH="$1"
  case "$TARGET_PATH" in
    /*) ABSOLUTE_PATH="$TARGET_PATH" ;;
    *) ABSOLUTE_PATH="$PWD/$TARGET_PATH" ;;
  esac

  PATH_SUFFIX=""
  while [ ! -e "$ABSOLUTE_PATH" ] && [ ! -L "$ABSOLUTE_PATH" ]; do
    PATH_SUFFIX="/$(basename -- "$ABSOLUTE_PATH")$PATH_SUFFIX"
    PARENT_PATH="$(dirname -- "$ABSOLUTE_PATH")"
    [ "$PARENT_PATH" != "$ABSOLUTE_PATH" ] || return 1
    ABSOLUTE_PATH="$PARENT_PATH"
  done

  RESOLVED_PATH="$(realpath "$ABSOLUTE_PATH")" || return 1
  printf '%s%s\n' "$RESOLVED_PATH" "$PATH_SUFFIX"
}

case "$MODE" in
  clear)
    [ -z "$SID" ] && exit 0
    if [ -e "$STATE_DIR" ] || [ -L "$STATE_DIR" ]; then
      state_dir_is_safe || exit 1
    else
      exit 0
    fi
    rm -f "$HIGH_FLAG" "$MEDIUM_FLAG" "$FETCH_FLAG"
    exit 0
    ;;

  set)
    [ -z "$SID" ] && exit 0
    prepare_state_dir || exit 1
    TOOL=$(printf '%s' "$INPUT" | jq -r '.tool_name // ""')
    SEVERITY=$(printf '%s' "$INPUT" | jq -r '.tool_input.severity // ""')
    case "$TOOL:$SEVERITY" in
      mcp__code-lesson__list_lessons_for_stack:high|mcp__code-lesson-kms__list_lessons_for_stack:high)
        create_flag "$HIGH_FLAG" || exit 1
        ;;
      mcp__code-lesson__list_lessons_for_stack:medium|mcp__code-lesson-kms__list_lessons_for_stack:medium)
        create_flag "$MEDIUM_FLAG" || exit 1
        ;;
      mcp__code-lesson__get_lessons_by_ids:*|mcp__code-lesson-kms__get_lessons_by_ids:*)
        if valid_flag "$HIGH_FLAG" &&
          valid_flag "$MEDIUM_FLAG" &&
          printf '%s' "$INPUT" | jq -e '
            .tool_input.ids |
            type == "array" and
            length > 0 and
            all(.[]; type == "string" and length > 0)
          ' >/dev/null; then
          create_flag "$FETCH_FLAG" || exit 1
        fi
        ;;
    esac
    exit 0
    ;;

  check)
    FILE_PATH=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // ""')
    [ -z "$FILE_PATH" ] && emit_deny && exit 0

    case "/$FILE_PATH/" in
      */../*|*/./*)
        emit_deny
        exit 0
        ;;
    esac

    CANONICAL_FILE_PATH="$(canonicalize_target "$FILE_PATH")" || {
      emit_deny
      exit 0
    }

    # Path-based skips: workflow artifacts and build output never trigger the gate.
    case "$CANONICAL_FILE_PATH" in
      "$WORKSPACE_ROOT"/*)
        WORKSPACE_RELATIVE_PATH="${CANONICAL_FILE_PATH#"$WORKSPACE_ROOT"/}"
        case "/$WORKSPACE_RELATIVE_PATH/" in
          */tickets/*|*/.planning/*|*/sessions/*|*/.claude/*|*/.git/*|*/node_modules/*|*/dist/*|*/build/*|*/.next/*|*/coverage/*)
            exit 0 ;;
        esac
        ;;
    esac

    # Extension-based gate: only fires on real code files.
    case "$CANONICAL_FILE_PATH" in
      *.ts|*.tsx|*.js|*.jsx|*.mjs|*.cjs|*.py|*.go|*.sh|*.bash|*.zsh|*.sql|*.css|*.scss|*.html|*.vue|*.svelte|*.rs|*.java|*.kt|*.swift|*.rb|*.php)
        ;;
      *)
        exit 0 ;;
    esac

    if [ -n "$SID" ] &&
      prepare_state_dir &&
      valid_flag "$HIGH_FLAG" &&
      valid_flag "$MEDIUM_FLAG" &&
      valid_flag "$FETCH_FLAG"; then
      exit 0
    fi

    emit_deny
    exit 0
    ;;

  *)
    emit_deny
    exit 0
    ;;
esac
