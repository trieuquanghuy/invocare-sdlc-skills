#!/usr/bin/env bash
# UserPromptSubmit hook: deny prompts that leak confidential material.
# Claude Code expands @<path> mentions as context injection BEFORE PreToolUse
# hooks can see them, so we must block at prompt-submit time.
#
# Blocks when the prompt contains:
#   1. @-mention of a confidential file path
#        - .env or .env.<variant>          (dotenv incl. .env.local, .env.firehawk-ivc-dev)
#        - service-keys<variant>           (service account / key files)
#        - environment.ts / environment.<variant>.ts   (Angular env files)
#   2. A literal API key or private key (pasted secret)
set -euo pipefail

input=$(cat)
prompt=$(printf '%s' "$input" | jq -r '.prompt // ""')

file_pattern='@[^[:space:]]*(\.env(\.[A-Za-z0-9_.-]+)?|service-keys[A-Za-z0-9_.-]*|environment(\.[A-Za-z0-9_-]+)?\.ts)([^A-Za-z0-9]|$)'

if printf '%s' "$prompt" | grep -qE "$file_pattern"; then
  jq -n '{
    decision: "block",
    reason: "Blocked by project hook: @-mention of confidential files (.env*, service-keys*, environment*.ts) is not allowed. See .claude/hooks/block-confidential-prompt.sh."
  }'
  exit 0
fi

# Known-vendor secret formats. Length thresholds keep false positives low.
secret_pattern='(sk-ant-[A-Za-z0-9_-]{95,}|sk-proj-[A-Za-z0-9_-]{40,}|sk-[A-Za-z0-9]{48}|AKIA[0-9A-Z]{16}|AIza[A-Za-z0-9_-]{35}|(gh[pousr]|github_pat)_[A-Za-z0-9_]{36}|xox[baprs]-[A-Za-z0-9-]{20,}|sk_(live|test)_[A-Za-z0-9]{24}|-----BEGIN [A-Z ]*PRIVATE KEY-----)'

if printf '%s' "$prompt" | grep -qE "$secret_pattern"; then
  jq -n '{
    decision: "block",
    reason: "Blocked by project hook: prompt appears to contain an API key or private key (Anthropic / OpenAI / AWS / Google / GitHub / Slack / Stripe / PEM). Scrub secrets before submitting. See .claude/hooks/block-confidential-prompt.sh."
  }'
  exit 0
fi

exit 0
