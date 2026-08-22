#!/bin/bash
# task-status batch-1 extractor: every local fact + git scan in one call.
# Usage: extract.sh TICKET_KEY   (run from the InvoCare project root, or set INVOCARE_ROOT)
set -u
KEY="${1:?usage: extract.sh TICKET_KEY}"
BASE="${INVOCARE_ROOT:-$(pwd)}"
K="$BASE/tickets/$KEY"

echo "=== FILES ==="
ls -la "$K" 2>/dev/null; ls "$K/notes" 2>/dev/null

echo "=== SESSION-LOG RUNS (env/date/action per run) ==="
grep -E '^## Run|^\- \*\*(Session ID|Environment|Date|Action|Notes acknowledged)' "$K/session-log.md" 2>/dev/null

echo "=== LATEST RUN SECTION (paths for drift check) ==="
awk '/^## Run /{s=NR} {l[NR]=$0} END{for(i=s;i<=NR;i++) print l[i]}' "$K/session-log.md" 2>/dev/null | head -60

echo "=== RCA (currency + confluence) ==="
grep -E 'CURRENT|PARTIALLY_STALE|OUTDATED|Confluence' "$K/rca.md" 2>/dev/null | head -5

echo "=== SPEC (fix type + repos) ==="
grep -iE 'fix type|classification|repo' "$K/spec.md" 2>/dev/null | head -8

echo "=== VALIDATION SCENARIOS ==="
grep -E '^#{2,3} |^\| *(TC|S[0-9])' "$K/validation.md" 2>/dev/null | head -25

echo "=== NOTES (first 3 lines each) ==="
for n in "$K"/notes/*-apply-findings.md; do
  [ -f "$n" ] && echo "--- $(basename "$n")" && head -3 "$n"
done

echo "=== LAST-CHECKED ==="
cat "$K/.last-checked" 2>/dev/null; echo

echo "=== GIT COMMITS ==="
REPOS="FCRM-Web FCRM-Cloud-Functions FCRM-Cloud-App FCRM-Exports-API FCRM-Reports-API FCRM-Email-API FCRM-Files-API Barndoor-Auth-App Barndoor-Batch-App"
found=0; total=0
for repo in $REPOS; do
  total=$((total+1))
  if [ -d "$BASE/$repo/.git" ]; then
    found=$((found+1))
    git -C "$BASE/$repo" log --all --oneline --grep="$KEY" | sed "s/^/$repo: /"
  else
    echo "$repo: (not present locally — skipping)"
  fi
done
[ "$found" -eq 0 ] && echo "⚠️ 0 of $total repos under \$BASE=$BASE — set INVOCARE_ROOT or run from project root"
exit 0
