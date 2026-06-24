#!/usr/bin/env bash
# PostToolUse hook: after a code-lessons SKIM (list_lessons_for_stack), write
# a per-(session, language, severity) sentinel so the PreToolUse Edit/Write
# gate can verify that BOTH "high" AND "medium" severities have been skimmed
# for that language. The language and severity are read from
# list_lessons_for_stack's tool_input. Paired with check-lessons-fetched.sh
# (PreToolUse) and clear-lessons-sentinel.sh (PreCompact).
#
# Severity filtering in the code-lessons corpus is EXCLUSIVE — a single
# "high" call does NOT cover "medium". The gate requires two calls; this
# hook records each one independently.
#
# Only "high" and "medium" sentinels are tracked. "critical" and "low" calls
# are useful but not gated, so they're ignored to keep the sentinel surface
# small.
set -euo pipefail

input=$(cat)
session_id=$(printf '%s' "$input" | jq -r '.session_id // empty')
language=$(printf '%s' "$input" | jq -r '.tool_input.language // empty')
severity=$(printf '%s' "$input" | jq -r '.tool_input.severity // empty')

[ -z "$session_id" ] && exit 0
[ -z "$language" ] && exit 0
[ -z "$severity" ] && exit 0

case "$severity" in
  high|medium) ;;
  *) exit 0 ;;
esac

touch "/tmp/claude-lessons-fetched-$session_id-$language-$severity"
exit 0
