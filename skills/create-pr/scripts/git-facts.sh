#!/usr/bin/env bash
# git-facts.sh — read-only fact capture for /create-pr.
#
# Usage:
#   git-facts.sh {repo_path} {ticket_key}          # per-repo fact block (Step 0d)
#   git-facts.sh --discover {base_dir} {ticket_key} # multi-repo discovery (Step 0c)
#
# Read-only: the only network call is `git fetch origin` (refreshes remote
# refs; never touches the working tree, branches, or index).
set -u

G7_PATTERN='(^|/)(node_modules|dist|build|\.next|out|coverage|__pycache__|\.cache|\.idea)(/|$)|(^|/)(\.DS_Store|Thumbs\.db|desktop\.ini)$|\.(pyc|pyo|class|o|so|dll|exe|swp|swo)$|~$|\.log$'

resolve_base() {
  # develop preferred, main fallback (team branching strategy)
  if git rev-parse --verify -q origin/develop >/dev/null; then
    echo develop
  elif git rev-parse --verify -q origin/main >/dev/null; then
    echo main
  elif git rev-parse --verify -q origin/master >/dev/null; then
    echo master
  else
    echo ""
  fi
}

if [ "${1:-}" = "--discover" ]; then
  BASE_DIR="${2:?usage: git-facts.sh --discover base_dir ticket_key}"
  TICKET="${3:?ticket key required}"
  for dir in "$BASE_DIR"/*/; do
    repo="$(basename "$dir")"
    [ -d "$dir/.git" ] || continue
    if ! git -C "$dir" rev-parse --verify -q origin/main >/dev/null \
       && ! git -C "$dir" rev-parse --verify -q origin/develop >/dev/null; then
      echo "WARN: $repo — no origin/main or origin/develop, skipped"
      continue
    fi
    hashes=$(git -C "$dir" log --all --grep="$TICKET" --no-merges \
               --not origin/main origin/develop --pretty=%H 2>/dev/null)
    [ -n "$hashes" ] || continue
    count=$(printf '%s\n' "$hashes" | wc -l | tr -d ' ')
    first=$(git -C "$dir" log --all --grep="$TICKET" --no-merges \
              --not origin/main origin/develop --oneline 2>/dev/null | tail -1)
    echo "CANDIDATE: $repo | $count commit(s) | $first"
  done
  exit 0
fi

REPO="${1:?usage: git-facts.sh repo_path ticket_key}"
TICKET="${2:?ticket key required}"
cd "$REPO" || { echo "ERROR: cannot cd to $REPO"; exit 1; }

echo "== fetch =="
git fetch origin 2>&1 | tail -3

BASE="$(resolve_base)"
echo "== base =="
echo "${BASE:-NONE (no origin/develop, main, or master)}"

echo "== status_porcelain =="
git status --porcelain

echo "== current_branch =="
git symbolic-ref --short -q HEAD || echo "DETACHED"

echo "== ahead_behind =="
if [ -n "$BASE" ]; then
  echo "ahead: $(git rev-list --count "origin/$BASE..HEAD" 2>/dev/null || echo '?')"
  echo "behind: $(git rev-list --count "HEAD..origin/$BASE" 2>/dev/null || echo '?')"
else
  echo "ahead: ?  behind: ?  (no base)"
fi

echo "== dangerous_state =="
for marker in rebase-apply rebase-merge; do
  [ -d ".git/$marker" ] && echo "$marker: IN PROGRESS"
done
for marker in MERGE_HEAD CHERRY_PICK_HEAD BISECT_LOG; do
  [ -f ".git/$marker" ] && echo "$marker: IN PROGRESS"
done
echo "ok (any lines above are in-progress ops)"

echo "== unresolved_conflicts =="
git diff --name-only --diff-filter=U

echo "== diff_stat_vs_base =="
[ -n "$BASE" ] && git diff "origin/$BASE..HEAD" --stat | tail -20

echo "== hygiene_scan =="
if [ -n "$BASE" ]; then
  git diff --name-only "origin/$BASE..HEAD" | grep -E "$G7_PATTERN" || echo "clean"
fi

echo "== ticket_commits =="
if [ -n "$BASE" ]; then
  git log --all --grep="$TICKET" --no-merges --not "origin/$BASE" --reverse --oneline
fi
