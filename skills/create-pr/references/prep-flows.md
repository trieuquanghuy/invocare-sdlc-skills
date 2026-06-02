# create-pr Prep Flows — Operator Reference

A maintainer's reference for the prep states `create-pr` recognizes. This file is NOT shown to operators — they see prompts and refuse messages from `SKILL.md` directly. Read this when:

- You're maintaining the skill and need a quick refresh of the state machine
- You're debugging a `/create-pr` invocation and need to map an observed prompt back to the state that produced it
- You hit the conflict gate while operating and want a copy-paste rollback recipe to keep next to your terminal

**Step numbering note:** SKILL.md uses Steps 0a → 0f. Step 0c is multi-repo discovery (no repo arg). Step 0d captures per-repo facts including ticket commits. Step 0e classifies state. Step 0f runs the prep flow (A / B / C).

---

## State decision tree

`create-pr` runs Step 0e on entry to classify the current git state into exactly one of these (top-most matching row wins — order matters):

| State | Conditions | What the skill does |
|-------|-----------|---------------------|
| **Refuse: dangerous git state** | Detached HEAD, in-progress rebase / merge / cherry-pick / bisect, OR unresolved conflicts | Exit. User resolves the in-progress operation manually. |
| **Refuse: no ticket commits** | `git log --all --grep="{TICKET_KEY}" --no-merges --not origin/{BASE}` returns empty | Exit. User must commit ticket work before re-running. |
| **Already prepped** | On non-base branch + ≥1 commit ahead + clean tree + EVERY non-merge commit in `{BASE}..HEAD` references `{TICKET_KEY}` + no in-progress op | Skip Step 0f, go to Step 1 (lessons review). |
| **Flow C — polluted ticket branch** | Ticket commits exist AND (the current branch has them + cross-ticket commits in `{BASE}..HEAD`, OR working tree is dirty with files outside the ticket commits' file set, OR ticket commits live on a different branch from current) | Run Step 0f — Flow C. |
| **Flow A — rescue** | On `main` or `develop` + non-empty `git status --porcelain` | Run Step 0f — Flow A. |
| **Flow B — fresh** | On `main` or `develop` + clean tree + no in-progress git op | Run Step 0f — Flow B. |

Flow C is the catch-all for the common case: user has been working on a ticket, committed some of it, has unrelated churn elsewhere in the tree. Flow C cherry-picks the ticket commits onto a clean branch off `origin/{BASE}` and stashes the rest. The previous "Refuse: dirty feature branch" state is gone.

---

## Flow A — operations

```
1. git fetch origin
2. git stash push -u -m "create-pr-prep-{TICKET_KEY}"
3. git switch {BASE}                              # 'main' or 'develop'
4. git pull --ff-only
5. git switch -c {NEW_BRANCH}
6. git stash pop
   ↑ may produce conflicts — see § Conflict gate
```

Steps 1–5 are non-interactive once the user types `yes` at the confirmation gate. Step 6 may pause and wait for user input if conflicts surface.

---

## Flow B — operations

```
1. git fetch origin
2. git switch {BASE}                              # skip if already on it
3. git pull --ff-only
4. git switch -c {NEW_BRANCH}
```

No conflict gate — the working tree is clean by definition. Like Flow A, Flow B runs through the confirmation gate (next section) before executing — both flows ask the user once before any state change.

---

## Flow C — operations

```
1. git fetch origin
2. (if dirty)
   git stash push -u -m "create-pr-prep-{TICKET_KEY}"   # untracked + dirty → stash
3. git switch -c {NEW_BRANCH} origin/{BASE}             # clean branch off target base
4. for sha in TICKET_COMMITS (chronological order):
     git cherry-pick {sha}
     # on conflict: pause at the cherry-pick conflict gate (see below)
   end for
5. NO auto stash pop. Stash entry stays so user controls its fate.
```

Key differences vs Flow A:
- Branch cut from `origin/{BASE}`, not from local `{BASE}` (so even a stale local base is bypassed)
- Stash is NEVER popped automatically — the contents are out-of-scope by definition
- Conflict gate is for cherry-pick conflicts, not stash-pop conflicts (different surface)

### Cherry-pick conflict gate (Flow C only)

After any cherry-pick that exits non-zero with conflicts (markers present, `git status` shows unmerged paths):

```
⚠️  Cherry-pick of {SHA} produced conflicts in {N} file(s):
  - {file 1}
  - {file 2}

Resolve them in your editor (or another terminal):
  - Edit each file, remove conflict markers
  - git add <resolved files>
  - git cherry-pick --continue
  - (or git cherry-pick --abort to bail out of this cherry-pick)

Type 'continue' when done, or 'abort' to exit.
```

| Response | Effect |
|----------|--------|
| `continue` | Re-check unmerged paths. If clean → proceed to next cherry-pick. If still dirty → list and re-prompt. |
| `abort` | Print recovery recipe (`git cherry-pick --abort && git switch {ORIGINAL_BRANCH}`) and exit. |

### Flow C abort recipe

If you `abort` at the cherry-pick conflict gate (or any time Flow C exits mid-prep):

```
# Abort the in-progress cherry-pick (does NOT touch other commits)
git cherry-pick --abort

# Return to the original branch you were on before Flow C started
git switch {ORIGINAL_BRANCH}

# Delete the new branch (it had partial commits)
git branch -D {NEW_BRANCH}

# Recover stash (if step 2 stashed work):
git stash list                 # find "create-pr-prep-{TICKET_KEY}"
git stash pop stash@{N}        # restore working-tree state
```

The skill never attempts this automatically — too much state can have changed mid-resolution.

---

## Branch name format

Final shape: `feature/{TICKET_KEY}-{kebab-description}` capped at 60 chars.

Per the team Git Branching & Release Strategy (Confluence page id `327043186731`), every sprint-level ticket — regardless of Jira `issuetype.name` (Bug, Defect, Story, Task, Sub-task, Epic) — uses the `feature/` prefix. Sprint-level bug fixes are still `feature/*` work, not `hotfix/*`. The `hotfix/*` and `release/*` prefixes are reserved for the manual semver flows and are out of scope for this skill.

| Prefix | Used by this skill? | Source |
|---|---|---|
| `feature/` | YES — every ticket | Confluence: feature branches for in-sprint work |
| `release/` | NO — out of scope (manual semver flow) | Confluence: cut from `develop`, target `main` + back-merge to `develop` |
| `hotfix/` | NO — out of scope (manual semver flow) | Confluence: cut from a release tag on `main`, target `main` + back-merge to `develop` |

| Source for description (first match wins) | Notes |
|-------------------------------------------|-------|
| `tickets/{TICKET_KEY}/spec.md` first H1 | Preferred — already team-verified phrasing |
| `tickets/{TICKET_KEY}/rca.md` first H1 | Fallback if spec missing |
| Jira ticket Summary field | Fallback if both missing |
| Ask user | Last resort |

Transform: lowercase → replace non-alphanumeric runs with single hyphen → strip leading/trailing hyphens → truncate at last word boundary if over budget.

Example: `feature/GEN-2759-template-filename-mismatch`

---

## Confirmation gate

Before executing any state-changing operation, `create-pr` shows the full plan once and asks for one confirmation:

```
Detected: Flow A — rescue from base
Base:     develop
Branch:   feature/GEN-2759-template-filename-mismatch  (issuetype=Bug, source=spec.md)

Will run:
  1. git fetch origin
  2. git stash push -u -m "create-pr-prep-GEN-2759"
  3. git switch develop
  4. git pull --ff-only
  5. git switch -c feature/GEN-2759-template-filename-mismatch
  6. git stash pop

Proceed? (yes / edit-branch / no)
```

| Response | Effect |
|----------|--------|
| `yes` | Execute all operations sequentially. Stop on first failure. |
| `edit-branch` | Prompt for new branch name; validate; re-show the plan |
| `no` | Exit. No state changes were made (the plan was shown but not executed). |

---

## Conflict gate (Flow A only)

After Flow A step 6 (`git stash pop`), the skill checks for conflicts:

```
git diff --name-only --diff-filter=U
git ls-files -u
```

If either returns non-empty, the skill enters the conflict gate:

```
⚠️  Stash pop produced conflicts in 3 file(s):
  - src/forms/FormController.ts
  - src/forms/types.ts
  - src/forms/utils.ts

Resolve them in your editor (or another terminal):
  - Edit each file, remove conflict markers
  - git add <resolved files>
  - (optional) git stash drop  ← drops the redundant stash entry

Type 'continue' when done, or 'abort' to exit.
```

| Response | Effect |
|----------|--------|
| `continue` | Re-check both diff outputs. If clean → proceed to Step 1. If still dirty → list remaining conflicts, re-prompt. |
| `abort` | Exit on the new branch with conflicts present. Print the manual rollback recipe. |

---

## Abort recovery recipe

If you `abort` at the conflict gate (or any time the skill exits mid-prep), you'll be on the new branch with conflicts and possibly an applied stash. Manual rollback:

```
# Drop the new branch and return to the base
git switch {BASE}
git branch -D {NEW_BRANCH}

# If you want your original work back as a stash entry:
git stash list                 # find your entry — created with message "create-pr-prep-{TICKET_KEY}"
git stash apply stash@{N}      # restore it (use 'apply' not 'pop' so you keep the stash for safety)
```

The skill never attempts this rollback automatically — too much state can have changed mid-resolution. The recipe above is the human-driven path.

---

## Limitations

- `git stash -u` doesn't follow symlinks outside the worktree. If you have files in symlinked locations outside the repo, they aren't preserved by Flow A or Flow C's stash.
- The skill assumes `origin` is the GitHub Enterprise remote. Multi-remote setups (e.g. an upstream + a fork) require the user to ensure `git pull --ff-only` (Flow A/B) or `git switch -c …  origin/{BASE}` (Flow C) runs against the right remote — the skill does not specify a remote on `pull`/`switch`.
- Branch-name collision is detected against local refs in Step 0f.2. Unlike previous versions, the skill does NOT refuse on collision — it auto-suffixes (`-pr`, `-pr-2`, …) and surfaces the chosen name in the prep plan. Race conditions where the same name appears on the remote between Step 0d's fetch and Step 3's push are caught by checker rule P22.
- Flow C's ticket-commit discovery uses `git log --grep`. Commits whose messages do NOT contain the ticket key are invisible to the skill, even if their files belong to the ticket. The user must include `{TICKET_KEY}` in commit messages for this skill to find them — there is no fallback heuristic on file paths.
