#!/usr/bin/env bash
# PreToolUse hook: deny tool calls that target confidential files.
# Blocks Read / Grep / Glob / Bash when the target references:
#   - .env or .env.<variant>          (dotenv files incl. .env.local, .env.ts, .env.firehawk-ivc-dev)
#   - service-keys<variant>           (service account / key files)
#   - environment.ts or environment.<variant>.ts   (Angular env files)
set -euo pipefail

input=$(cat)
tool_name=$(printf '%s' "$input" | jq -r '.tool_name // ""')

target=""
case "$tool_name" in
  Read)
    target=$(printf '%s' "$input" | jq -r '.tool_input.file_path // ""')
    ;;
  Glob)
    target=$(printf '%s' "$input" | jq -r '[.tool_input.pattern, .tool_input.path] | map(select(. != null)) | join(" ")')
    ;;
  Grep)
    target=$(printf '%s' "$input" | jq -r '[.tool_input.path, .tool_input.glob, .tool_input.pattern] | map(select(. != null)) | join(" ")')
    ;;
  Bash)
    target=$(printf '%s' "$input" | jq -r '.tool_input.command // ""')
    ;;
  *)
    exit 0
    ;;
esac

# Single regex covering the three confidential-file shapes, anchored by a non-alphanumeric
# (or start/end) on each side so `events.ts`, `.envoy`, `environment.tsconfig` etc. don't false-match.
file_pattern='(^|[^A-Za-z0-9])(\.env(\.[A-Za-z0-9_.-]+)?|service-keys[A-Za-z0-9_.-]*|environment(\.[A-Za-z0-9_-]+)?\.ts)($|[^A-Za-z0-9])'

if printf '%s' "$target" | grep -qE "$file_pattern"; then
  jq -n '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: "Blocked by project hook: access to confidential files (.env*, service-keys*, environment*.ts) is not allowed. See .claude/hooks/block-confidential.sh."
    }
  }'
  exit 0
fi

# Known-vendor secret formats. Length thresholds keep false positives low.
secret_pattern='(sk-ant-[A-Za-z0-9_-]{95,}|sk-proj-[A-Za-z0-9_-]{40,}|sk-[A-Za-z0-9]{48}|AKIA[0-9A-Z]{16}|AIza[A-Za-z0-9_-]{35}|(gh[pousr]|github_pat)_[A-Za-z0-9_]{36}|xox[baprs]-[A-Za-z0-9-]{20,}|sk_(live|test)_[A-Za-z0-9]{24}|-----BEGIN [A-Z ]*PRIVATE KEY-----)'

if printf '%s' "$target" | grep -qE "$secret_pattern"; then
  jq -n '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: "Blocked by project hook: tool input appears to contain an API key or private key (Anthropic / OpenAI / AWS / Google / GitHub / Slack / Stripe / PEM). Scrub secrets before continuing. See .claude/hooks/block-confidential.sh."
    }
  }'
  exit 0
fi

exit 0
