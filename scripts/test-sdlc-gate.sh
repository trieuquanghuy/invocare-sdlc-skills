#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATE="$ROOT/.claude/scripts/sdlc-gate.sh"
TEST_ROOT="$(mktemp -d)"
export TMPDIR="$TEST_ROOT"
EXCLUDED_LINK="$ROOT/tickets/.sdlc-gate-test-link-$$"
trap 'rm -f "$EXCLUDED_LINK"; rm -rf "$TEST_ROOT"' EXIT

SID="test-sdlc-gate-$$"
CHECK_INPUT='{"session_id":"'"$SID"'","tool_input":{"file_path":"src/example.ts"}}'

run_gate() {
  printf '%s' "$CHECK_INPUT" | "$GATE" "$1"
}

assert_denied() {
  run_gate check | grep -q '"permissionDecision": "deny"'
}

assert_allowed() {
  ! run_gate check | grep -q '"permissionDecision": "deny"'
}

set_gate() {
  printf '%s' "$1" | "$GATE" set
}

set_gate '{"session_id":"'"$SID"'","tool_name":"mcp__code-lesson__list_lessons_for_stack","tool_input":{"severity":"high"}}'
assert_denied

set_gate '{"session_id":"'"$SID"'","tool_name":"mcp__code-lesson__list_lessons_for_stack","tool_input":{"severity":"medium"}}'
assert_denied

set_gate '{"session_id":"'"$SID"'","tool_name":"mcp__code-lesson__get_lessons_by_ids","tool_input":{"ids":["lesson-1"]}}'
assert_allowed

printf '%s' "$CHECK_INPUT" | "$GATE" clear
assert_denied

printf '%s' '{"tool_input":{"file_path":"src/example.ts"}}' | "$GATE" check | grep -q '"permissionDecision": "deny"'

EMPTY_SID="$SID-empty"
set_gate '{"session_id":"'"$EMPTY_SID"'","tool_name":"mcp__code-lesson__list_lessons_for_stack","tool_input":{"severity":"high"}}'
set_gate '{"session_id":"'"$EMPTY_SID"'","tool_name":"mcp__code-lesson__list_lessons_for_stack","tool_input":{"severity":"medium"}}'
set_gate '{"session_id":"'"$EMPTY_SID"'","tool_name":"mcp__code-lesson__get_lessons_by_ids","tool_input":{"ids":[]}}'
printf '%s' '{"session_id":"'"$EMPTY_SID"'","tool_input":{"file_path":"src/example.ts"}}' |
  "$GATE" check |
  grep -q '"permissionDecision": "deny"'

TRAVERSAL_SID="$SID-traversal"
set_gate '{"session_id":"'"$TRAVERSAL_SID"'","tool_name":"mcp__code-lesson__list_lessons_for_stack","tool_input":{"severity":"high"}}'
set_gate '{"session_id":"'"$TRAVERSAL_SID"'","tool_name":"mcp__code-lesson__list_lessons_for_stack","tool_input":{"severity":"medium"}}'
set_gate '{"session_id":"'"$TRAVERSAL_SID"'","tool_name":"mcp__code-lesson__get_lessons_by_ids","tool_input":{"ids":["lesson-1"]}}'
printf '%s' '{"session_id":"'"$TRAVERSAL_SID"'","tool_input":{"file_path":"src/../tickets/escape.ts"}}' |
  "$GATE" check |
  grep -q '"permissionDecision": "deny"'

EXCLUDED_PATH="$ROOT/tickets/.sdlc-gate-test-normal-$$/notes.ts"
printf '%s' '{"session_id":"excluded-path","tool_input":{"file_path":"'"$EXCLUDED_PATH"'"}}' |
  "$GATE" check |
  test -z "$(cat)"

SYMLINK_TARGET="$TEST_ROOT/real-ticket-files"
mkdir -p "$SYMLINK_TARGET"
ln -s "$SYMLINK_TARGET" "$EXCLUDED_LINK"
EXCLUDED_PATH="$EXCLUDED_LINK/notes.ts"
printf '%s' '{"session_id":"excluded-symlink","tool_input":{"file_path":"'"$EXCLUDED_PATH"'"}}' |
  "$GATE" check |
  grep -q '"permissionDecision": "deny"'

SYMLINK_TMP="$TEST_ROOT/symlink-tmp"
VICTIM_DIR="$TEST_ROOT/victim-dir"
mkdir -p "$SYMLINK_TMP" "$VICTIM_DIR"
ln -s "$VICTIM_DIR" "$SYMLINK_TMP/claude-sdlc-gate"
printf '%s' '{"session_id":"symlink-dir","tool_name":"mcp__code-lesson__list_lessons_for_stack","tool_input":{"severity":"high"}}' |
  TMPDIR="$SYMLINK_TMP" "$GATE" set || true
test -z "$(find "$VICTIM_DIR" -mindepth 1 -print -quit)"

FLAG_SID="symlink-flag"
FLAG_KEY="$(printf '%s' "$FLAG_SID" | shasum -a 256 | awk '{print $1}')"
STATE_DIR="$TEST_ROOT/claude-sdlc-gate"
VICTIM_FILE="$TEST_ROOT/victim-file"
mkdir -p "$STATE_DIR"
printf 'keep' > "$VICTIM_FILE"
ln -s "$VICTIM_FILE" "$STATE_DIR/$FLAG_KEY.high"
set_gate '{"session_id":"'"$FLAG_SID"'","tool_name":"mcp__code-lesson__list_lessons_for_stack","tool_input":{"severity":"high"}}' || true
test "$(cat "$VICTIM_FILE")" = "keep"
