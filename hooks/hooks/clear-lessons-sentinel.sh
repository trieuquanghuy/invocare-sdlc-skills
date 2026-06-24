#!/usr/bin/env bash
# PreCompact hook: clear ALL per-(session, language) lessons sentinels before
# the harness compacts conversation context. After compaction the fetched
# lesson content may be summarized out of working memory, so the next
# Edit/Write per language should re-anchor by fetching again.
# Paired with check-lessons-fetched.sh and mark-lessons-fetched.sh.
set -euo pipefail

session_id=$(jq -r '.session_id // empty')
[ -z "$session_id" ] && exit 0

# Glob-delete every language sentinel for this session.
rm -f /tmp/claude-lessons-fetched-"$session_id"-*
# Also clean up any legacy non-language-keyed sentinel from the previous design.
rm -f "/tmp/claude-lessons-fetched-$session_id"
exit 0
