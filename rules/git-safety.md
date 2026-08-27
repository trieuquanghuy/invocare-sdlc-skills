# Git Safety — Common Pitfalls Every Git-Touching Skill Must Avoid

Applies to every skill that runs git or `gh` commands: `apply-fix`, `create-pr`, `task-status` (read-side), and any future skill that touches the git tree, branches, or remotes. Cited from `CLAUDE.md` so all skills inherit it.

These rules cover the universal git pitfalls. Skill-specific git behavior (branch naming for PRs, session-log conventions for Firebase writes, etc.) lives in the individual skill's `SKILL.md`, not here.

---

## G1 — Never push to a base branch

`main`, `master`, `develop`, or any branch designated as a base for PRs is off-limits for direct push. PRs are the only way changes land on these branches.

**Forbidden commands:** `git push origin main`, `git push origin master`, anything that would update a base branch ref directly.

**Detection:** inspect every push refspec before execution and refuse when its destination is `main`, `master`, `develop`, or any configured/designated base branch, regardless of the current branch. A feature branch does not authorize pushing its commit to a protected destination ref. Base branches are updated only by merging an approved PR through the team's review tooling.

---

## G2 — Never use destructive flags

The following flags and operations are unconditionally forbidden for automated execution. User-supplied flags or confirmation do not authorize a skill or agent to run them:

- `--force`, `-f` (push)
- `--force-with-lease` (push — slightly safer than `--force` but still rewrites remote history)
- `--no-verify`, `-n` (commit/push — bypasses pre-commit / pre-push hooks)
- `--hard` (reset — irrecoverable except via reflog within 30 days)
- `git clean -f`

**Why these are forbidden:** every one of them either rewrites shared history, bypasses safety nets, or destroys uncommitted work. None of them are appropriate for an automated skill to invoke.

**If a skill encounters a scenario where one of these flags would be useful** (e.g. recovering from a divergent remote), it MUST stop, explain the situation, and require the user to run the destructive command manually outside the skill. The automation never performs the operation itself.

---

## G3 — Never amend or rebase commits that have already been pushed to a remote

Once a commit is on any remote, history is shared. Before amend or rebase, enumerate every commit that would be rewritten and check whether it is reachable from any applicable remote ref (for example, with `git branch -r --contains <sha>`). If any remote contains a target commit, refuse. Divergence checks alone are insufficient because an equal or ahead-only branch may still include pushed commits.

If the user genuinely needs to fix a pushed commit, the skill stops and the user makes a NEW commit on top with an explanation.

---

## G4 — Never delete branches automatically

`git branch -D <branch>`, `git push origin --delete <branch>`, and similar are off-limits. Skills create branches; they don't tear them down. The user (or PR-merge automation) handles branch deletion.

---

## G5 — Never write to `.git/config` or change git settings

Skills run git commands; they don't modify the user's git configuration. No `git config --global`, no `git config user.email`, no rewriting hooks under `.git/hooks/`.

If a skill needs a particular git setting (e.g. `core.autocrlf`), the skill checks for it and surfaces the requirement to the user, who sets it themselves.

---

## G6 — Refuse on dangerous git states

A skill MUST refuse to make state-changing operations when the repo is in any of:

- **Detached HEAD** (`git symbolic-ref HEAD` exits non-zero)
- **In-progress rebase** (`.git/rebase-apply/` or `.git/rebase-merge/` exists)
- **In-progress merge** (`.git/MERGE_HEAD` exists)
- **In-progress cherry-pick** (`.git/CHERRY_PICK_HEAD` exists)
- **In-progress bisect** (`.git/BISECT_LOG` exists)
- **Unresolved conflicts** (`git diff --name-only --diff-filter=U` is non-empty)

Skills surface the specific state and the recovery commands (`git rebase --continue` / `--abort`, `git merge --abort`, etc.) and exit. They never try to "auto-fix" a broken state.

---

## G7 — Diff hygiene: no build artifacts, OS files, or editor cruft

Before any push or PR creation, scan `git diff --name-only {BASE}..HEAD` for the following patterns. If matched, refuse:

- **Directories:** `node_modules/`, `dist/`, `build/`, `.next/`, `out/`, `coverage/`, `__pycache__/`, `.cache/`, `.idea/`
- **OS files:** `.DS_Store`, `Thumbs.db`, `desktop.ini`
- **Compiled / generated:** `*.pyc`, `*.pyo`, `*.class`, `*.o`, `*.so`, `*.dll`, `*.exe`
- **Editor temp:** `*.swp`, `*.swo`, `*~`, `.netrwhist`
- **Logs** (other than committed sample logs in `samples/`, `examples/`, `fixtures/`, `docs/`): paths matching `*.log`

For each match, the recovery is the same: add the pattern to `.gitignore`, run `git rm --cached <file>`, commit the cleanup, and re-run.

---

## G8 — No secret values in the diff

Before commit, scan added lines in both the working-tree diff and staged index. Before push, also scan the complete outgoing commit range for every destination. Any match MUST stop the operation. Patterns:

- AWS access keys: `AKIA[A-Z0-9]{16}`
- Slack tokens: `xox[pbar]-`
- GitHub PATs: `ghp_[A-Za-z0-9]{36,}`
- JWTs: `eyJ[A-Za-z0-9_-]{20,}\.eyJ`
- PEM keys: `-----BEGIN [A-Z ]*PRIVATE KEY-----`
- Literal password assignments: `password\s*[:=]\s*["'][^"']+["']`
- Generic secrets: `(secret|token|api[_-]?key|client[_-]?secret)\s*[:=]\s*["'][A-Za-z0-9/+_=]{16,}["']`

This rule is the operational counterpart to `secrets-safety.md`. The user must remove the secret AND rotate it (the value entered git's reflog the moment they ran `git add`).

When citing the offending line in user-facing output, cite **only the file:line**, never the matched value (per `secrets-safety.md`).

---

## G9 — Stop on any git or `gh` error; never retry

If a git or `gh` command exits non-zero, the skill stops, redacts credential-bearing URLs and secret-looking values, surfaces the remaining diagnostic text, and exits. It does NOT:

- Retry with the same command
- Retry with flags removed (e.g. drop `--ff-only` and retry `git pull`)
- Silently ignore and continue

Errors are signals about the state of the world; ignoring them is how data gets lost.

---

## G10 — Untracked + ignored files don't get auto-staged

When a skill commits, it MUST stage explicit paths (`git add path/to/file.ts`), never `git add .` or `git add -A` or `git add -u` blindly. Reason: untracked files in the working tree may include secrets, env files, or scratch work the user didn't mean to commit.

If a skill's commit step needs to stage many files, it lists them explicitly. If the list is too long to manage, that's a signal that the change is too big and should be split.

---

## G11 — Commits are a short subject line by default; no long body

Every commit a skill produces is a single Conventional-Commits-with-scope subject line. Do NOT pass a `-m "{body}"` second argument, do NOT auto-generate a bullet list of changes, and do NOT amend a prior commit to graft a body on.

```
git commit -m "{type}({TICKET_KEY}): {short developer-voice description of WHAT changed}"
```

Why subject-only is the default:
- The subject is what `git log --oneline` shows — it must be skimmable. The full detail of *why* lives in the PR description and the Jira ticket, which is where reviewers actually read it.
- An auto-generated body almost always reads as bot output (enumerated findings, restated diff, meta-phrases). A developer who knows the codebase writes one line that says what they did.

The subject describes **what changed in the code, not why or where the instruction came from**. Forbidden in the subject: meta-phrases (`address review feedback`, `apply review fixes`, `cr fixes`), internal review-tool vocab (`lesson finding`, `AI review`, `F1/F2`), and any AI/automation attribution (`Co-Authored-By: Claude`, `🤖 Generated with Claude Code`) — the last is `output-guardian.md` applied to commits. Keep the subject ≤72 chars where possible; name the dominant theme rather than enumerating every touched area.

A commit body is permitted ONLY when the user explicitly asks for one in this turn. `/create-pr` Step 1f is the canonical implementation of this rule for review-fix commits; this is the baseline every committing skill inherits.

---

## Scope

This rule applies to:

- All Claude Code skills in this project (`.claude/skills/**`)
- All subagents dispatched by skills
- All output formats: file writes, terminal output, external posts (Jira, Confluence, GitHub PR bodies)

Skill-specific git rules (e.g. branch-naming convention for `create-pr`, session-log appending for `apply-fix`) live in the skill's own `SKILL.md` and may add to but never relax these baseline rules.
