#!/usr/bin/env bash
# PreToolUse hook: before any Edit/Write/MultiEdit, ensure code-lessons have
# been SKIMMED at BOTH severities ("high" AND "medium") for the language of
# the file being edited this session. Severity filtering in the code-lessons
# corpus is EXCLUSIVE — a "high" call returns only high-tagged lessons and a
# "medium" call returns only medium-tagged lessons, so a single call cannot
# cover both. The gate blocks until both per-(session, language, severity)
# sentinels exist.
#
# Paired with:
#   - mark-lessons-fetched.sh    (PostToolUse on list_lessons_for_stack, writes per-severity sentinel)
#   - clear-lessons-sentinel.sh  (PreCompact, glob-clears all per-session sentinels)
set -euo pipefail

input=$(cat)
session_id=$(printf '%s' "$input" | jq -r '.session_id // empty')
file_path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')

[ -z "$session_id" ] && exit 0

# Skip the gate entirely for non-code edits — docs, lockfiles, config,
# ticket writeups. Code lessons don't apply to these.
case "$file_path" in
  *.md|*.markdown|*.txt|*.rst) exit 0 ;;
  *.json|*.yaml|*.yml) exit 0 ;;
  *.lock|*/package-lock.json|*/yarn.lock|*/pnpm-lock.yaml|*/Gemfile.lock) exit 0 ;;
  *.gitignore|*.gitattributes|*.editorconfig) exit 0 ;;
  */tickets/*) exit 0 ;;
esac

# Infer language from file extension. Unknown extensions exit silent — we
# can't enforce what we can't classify.
case "$file_path" in
  *.ts|*.tsx)                  language=typescript ;;
  *.js|*.jsx|*.mjs|*.cjs)      language=javascript ;;
  *.py)                        language=python ;;
  *.swift)                     language=swift ;;
  *.php)                       language=php ;;
  *.go)                        language=go ;;
  *.rs)                        language=rust ;;
  *.rb)                        language=ruby ;;
  *.java)                      language=java ;;
  *.kt|*.kts)                  language=kotlin ;;
  *.sh|*.bash)                 language=bash ;;
  *.html|*.htm)                language=html ;;
  *.css|*.scss|*.sass|*.less)  language=css ;;
  *.twig)                      language=twig ;;
  *)                           exit 0 ;;
esac

base="/tmp/claude-lessons-fetched-$session_id-$language"
sentinel_high="$base-high"
sentinel_medium="$base-medium"

# Pass silently only when BOTH severities have been skimmed for this language.
if [ -f "$sentinel_high" ] && [ -f "$sentinel_medium" ]; then
  exit 0
fi

# Identify which severities are still missing so the block reason can name
# them explicitly.
missing=()
[ -f "$sentinel_high" ]   || missing+=("high")
[ -f "$sentinel_medium" ] || missing+=("medium")
missing_list=$(IFS=, ; echo "${missing[*]}")

reason=$(cat <<EOF
Pre-implementation gate (language=$language): code-lessons skim incomplete this session.

CLAUDE.md requires TWO skim calls per language. Severity filtering is EXCLUSIVE:
  - severity: "high"   returns ONLY high-tagged lessons
  - severity: "medium" returns ONLY medium-tagged lessons
A single call CANNOT cover both. Running only "high" silently drops the entire medium corpus and counts as a gate failure.

Missing for $language this session: $missing_list

Before retrying, run BOTH calls (and add "critical" on security-sensitive paths — auth, secrets, migrations, payments):

  mcp__code-lessons__list_lessons_for_stack({ language: "$language", frameworks: [...], severity: "high"   })
  mcp__code-lessons__list_lessons_for_stack({ language: "$language", frameworks: [...], severity: "medium" })

Two skims cost ~10K tokens and are cheap insurance against missing a known mistake. The single high-only path is acceptable ONLY for a genuinely trivial cosmetic edit (one-line CSS / hex tweak / typo-in-identifier) — and you must state that justification in the self-audit. Logic changes need both.

Identify ALL stacks your task will touch and bulk-skim each upfront. Common stacks in this monorepo:

  - typescript + angular   -> FCRM-Web, FCRM-Document-Signer, pdf-mapper
  - typescript + nestjs    -> Barndoor-Tributes-App
  - typescript + express   -> FCRM-Cloud-App, FCRM-Search-API, FCRM-Email-API, FCRM-Reports-API
  - typescript + firebase  -> FCRM-Cloud-Functions, FCRM-Funeral-Services-API
  - swift                  -> Firehawk-CRM-iOS
  - php                    -> FCRM-Tributes-WP-Plugin
  - twig                   -> document-templates

Pass only the language + frameworks actually imported in the touched files — never the full package.json. After both skims, call get_lessons_by_ids for the 3-10 relevant ids.

NOTE: the sentinel keys on (language, severity), NOT on framework. If your task spans multiple framework combos within the same language (e.g., typescript+angular AND typescript+nestjs), skim each combo separately — the gate cannot detect framework drift within a language.

After both severities are skimmed, retry the edit. Subsequent edits in any already-skimmed (language, both-severities) pair will pass silently. A first edit in a new language triggers the gate again.
EOF
)

jq -n --arg reason "$reason" '{
  decision: "block",
  reason: $reason
}'
exit 0
