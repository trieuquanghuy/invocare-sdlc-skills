#!/bin/bash
# SDLC gate: enforce code-lesson MCP pre-implementation gate at the harness layer.
# Reads Claude Code hook JSON from stdin. Three modes:
#   check   PreToolUse on Edit|Write — block code-file edits unless lesson MCP was called this task
#   set     PostToolUse on *         — record that a code-lesson MCP tool was just used
#   clear   UserPromptSubmit         — clear the sentinel so each new user prompt re-arms the gate
#
# See .claude/rules/sdlc-gates.md for the SDLC stages this enforces.

set -u

MODE="${1:-}"
INPUT=$(cat)
SID=$(printf '%s' "$INPUT" | jq -r '.session_id // ""')

# No session_id = malformed hook input. Don't break the user's flow.
[ -z "$SID" ] && exit 0

FLAG_FILE="/tmp/claude-sdlc-gate-${SID}.lesson-pulled"

case "$MODE" in
  clear)
    rm -f "$FLAG_FILE" 2>/dev/null
    exit 0
    ;;

  set)
    TOOL=$(printf '%s' "$INPUT" | jq -r '.tool_name // ""')
    case "$TOOL" in
      mcp__code-lesson__*|mcp__code-lesson-kms__*)
        touch "$FLAG_FILE"
        ;;
    esac
    exit 0
    ;;

  check)
    FILE_PATH=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // ""')
    [ -z "$FILE_PATH" ] && exit 0

    # Path-based skips: workflow artifacts and build output never trigger the gate.
    case "$FILE_PATH" in
      */tickets/*|*/.planning/*|*/sessions/*|*/.claude/*|*/.git/*|*/node_modules/*|*/dist/*|*/build/*|*/.next/*|*/coverage/*)
        exit 0 ;;
    esac

    # Extension-based gate: only fires on real code files.
    case "$FILE_PATH" in
      *.ts|*.tsx|*.js|*.jsx|*.mjs|*.cjs|*.py|*.go|*.sh|*.bash|*.zsh|*.sql|*.css|*.scss|*.html|*.vue|*.svelte|*.rs|*.java|*.kt|*.swift|*.rb|*.php)
        ;;
      *)
        exit 0 ;;
    esac

    # Code file. Gate fires unless the sentinel is present.
    if [ -f "$FLAG_FILE" ]; then
      exit 0
    fi

    # Emit a deny decision pointing the agent at the rule.
    cat <<'JSON'
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "SDLC GATE (.claude/rules/sdlc-gates.md Stage S1): code-lesson MCP has not been called for this task. Before editing this code file you MUST call mcp__code-lesson__list_lessons_for_stack at severity=\"high\" AND severity=\"medium\" (two separate calls — severity is an exclusive filter), then mcp__code-lesson__get_lessons_by_ids for the 3-10 relevant ids. If this change falls in the skip list (comment-only, pure whitespace, typo, non-code file), the gate should not have fired — surface the false positive to the user and they can override by adjusting .claude/scripts/sdlc-gate.sh."
  }
}
JSON
    exit 0
    ;;

  *)
    # Unknown mode — fail closed but quietly so a misconfigured hook doesn't block work.
    exit 0
    ;;
esac
