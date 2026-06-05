---
name: create-pr
description: "Use when ready to open a GitHub Enterprise pull request after code changes are committed locally. Triggers on: create PR, open pull request, ship branch, push to PR, gh pr create, raise PR for GEN-XXXX, multi-repo PR for one ticket."
argument-hint: "Jira ticket key (e.g. GEN-2759), optionally followed by a single repo name (e.g. FCRM-Web). Omit the repo to iterate across every repo with matching ticket commits. Append `hotfix` / `to main` / `to UAT` to switch from the default feature-to-develop flow into the Hotfix-to-Main workflow."
disable-model-invocation: true
---

# Create Pull Request

Open a pull request on GitHub Enterprise (`ivc.ghe.com`) for an InvoCare repo. For multi-repo tickets, can iterate across every repo under `$INVOCARE_ROOT` that has commits referencing the ticket key. Runs a code review against the team's lessons corpus before pushing, lets the user approve fixes, then creates the PR with the team's minimal title and body convention.

**Output guardian:** all output reads as written by a developer. Apply `.claude/rules/output-guardian.md` — never include tool names, MCP names, or any indication of automation in the PR title, body, or any visible artifact.

**Secrets safety:** apply `.claude/rules/secrets-safety.md` — the diff is scanned for secret-looking strings before push. If a match is found, the skill stops; the user must remove and rotate.

## Table of Contents

- [NOT This Skill If](#not-this-skill-if)
- [Prerequisites](#prerequisites)
- [Step 0: Resolve Ticket, Repos, and Ticket Commits](#step-0-resolve-ticket-repos-and-ticket-commits)
- [Step 0e: Detect Git State](#step-0e-detect-git-state)
- [Step 0f: Run Prep Flow (Flow A, Flow B, or Flow C)](#step-0f-run-prep-flow-flow-a-flow-b-or-flow-c)
- [Step 1: Code Review against Lessons Corpus](#step-1-code-review-against-lessons-corpus)
- [Step 2: Pre-flight Checker](#step-2-pre-flight-checker)
- [Step 3: Push the Branch](#step-3-push-the-branch)
- [Step 4: Generate Title and Body](#step-4-generate-title-and-body)
- [Step 5: Confirm with the User](#step-5-confirm-with-the-user)
- [Step 6: Create the PR](#step-6-create-the-pr)
- [Step 7: Summarize](#step-7-summarize)
- [Hotfix-to-Main Workflow (Promote to UAT)](#hotfix-to-main-workflow-promote-to-uat) → `references/hotfix-flow.md`
- [Rules](#rules) — the authoritative constraint list (Rules 1–25, mapped to checker P-rules)
- [Guardrails (single-page summary)](#guardrails-single-page-summary)
- [Quality Bar](#quality-bar)
- [Common Mistakes](#common-mistakes)
- [Next step](#next-step)

## NOT This Skill If

- Fix is Firebase config only with no code committed → use `/apply-fix`, then `/ticket-comment`.
- Code changes are not yet committed locally → commit first (with the ticket key in the commit message), then run `/create-pr`.
- User wants a draft PR or a non-ticket branch → not the use case; this skill produces a ready-for-review PR tied to a ticket key.
- User wants to merge an already-open PR → handle in the GitHub UI; this skill creates but does not merge.
- Work is a `release/*` branch → out of scope. The team Git Branching & Release Strategy (Confluence page id `327043186731`) defines `release/{semver}` as cut from `develop`, targeting `main`. Release PRs carry an entire sprint, not a single ticket — open them manually per the Confluence doc.
- `hotfix/*` IS supported via the **Hotfix-to-Main Workflow** below — use this when a single ticket needs to land on `main` ahead of the normal release cut (e.g. promote a fix for UAT verification on main builds, or ship an urgent prod fix). Default flow remains `feature/*` targeting `develop`.

---

## Prerequisites

- Ticket-relevant work is committed locally with the ticket key in at least one commit message (e.g. `feat(GEN-1945): ...`). The skill detects ticket commits via `git log --grep="{TICKET_KEY}"` — uncommitted work is out of scope.
- `gh` CLI authenticated for `ivc.ghe.com` (`gh auth status` shows it)
- `INVOCARE_ROOT` env var set (or run from inside a repo under it)
- Target repo(s) are InvoCare repos under `$INVOCARE_ROOT/`
- Working-tree files unrelated to the ticket (env churn, local configs, half-finished work) are allowed — Flow C will stash them automatically before cutting the PR branch. They never enter the PR diff.

---

## Step 0: Resolve Ticket, Repos, and Ticket Commits

**Step 0 — Mode selection: feature flow OR hotfix-to-main flow.**

Before resolving the ticket, decide which workflow runs:

| Mode | Target base | Argument triggers | When to use |
|------|-------------|-------------------|-------------|
| **feature** (default) | `develop` | `/create-pr {KEY}`, `/create-pr {KEY} {repo}` | Normal sprint work — committed on a feature branch, ready for peer review. |
| **hotfix** | `main` | `/create-pr {KEY} hotfix`, `/create-pr {KEY} to main`, `/create-pr {KEY} to uat`, `/create-pr {KEY} to UAT`, `/create-pr {KEY} --hotfix` | A single already-reviewed ticket needs to land on `main` ahead of the normal release cut. Cherry-picks commits already merged to `develop`. Requires Tech Lead approval on the PR. |

If hotfix mode is detected, **skip Steps 0a–7 and run the Hotfix-to-Main Workflow** (after Step 7). Step 0a (ticket-key resolution) and Step 0b (repo resolution) are still used by the hotfix flow's H1 (preflight) — they're cited from there.

**Step 0a: Resolve the ticket key.**

In order, first match wins:

1. Argument (`{TICKET_KEY}`)
2. `(GEN|FIR|IVC|PARK)-\d+` regex match in current branch name
3. The Jira ticket referenced in `tickets/` if exactly one ticket folder is "in flight" (last-modified within 7 days)
4. Otherwise: ask the user

If branch name and arg disagree (e.g. branch is `feature/GEN-2737-...` but arg is `GEN-2759`), warn and use the argument.

**Step 0b: Resolve target repo(s) — single-repo or multi-repo mode.**

```
BASE="${INVOCARE_ROOT:-$(pwd)}"
```

| Invocation | Mode | Action |
|------------|------|--------|
| `/create-pr GEN-XXXX FCRM-Web` | **single-repo** | Use `$BASE/FCRM-Web`. Skip 0c, go to 0d for that one repo. |
| `/create-pr GEN-XXXX` (no repo) | **multi-repo discovery** | Run Step 0c — scan every repo for ticket commits. |
| Repo path doesn't exist | error | Stop, report `Repo '{repo}' not found under {BASE}. Set INVOCARE_ROOT or pass the correct repo name`. |

**Step 0c: Multi-repo discovery (multi-repo mode only).**

For each subdirectory of `$BASE` that has a `.git/`, run:

```
git -C "$BASE/$repo" log --all --grep="{TICKET_KEY}" --no-merges \
  --not origin/main origin/develop --pretty=%H 2>/dev/null
```

A repo is a **candidate** if this command returns ≥1 commit hash. Skip repos that:
- Have no `.git/` (not initialised — print one-line note, continue)
- Return zero matching hashes (no work for this ticket — skip silently)
- Don't have `origin/main` AND don't have `origin/develop` (no recognised base — print warning, skip)

Output the candidate list to the user:

```
Found {N} repo(s) with commits for {TICKET_KEY}:
  - FCRM-Web: 1 commit ahead of develop (f70e057 feat(GEN-1945): route NZ branches…)
  - document-templates: 1 commit ahead of develop (78d0d85 feat(GEN-1945): add NZ Funeral Service…)

Process all? (yes / pick / no)
```

| Response | Effect |
|----------|--------|
| `yes` | Iterate every candidate. For each, run Steps 0d → 7 in sequence. Aggregate one summary at the end. |
| `pick` | Prompt for a comma-separated subset (e.g. `FCRM-Web`). Validate against the candidate list. |
| `no` | Exit. No state changes. |

If 0 candidates: refuse with:
```
No commits matching {TICKET_KEY} found in any local repo under {BASE}.

Make at least one commit whose message contains '{TICKET_KEY}' (e.g.
'feat({TICKET_KEY}): ...'), then re-run /create-pr.
```

**Step 0d: Per-repo prep — capture facts and detect ticket commits.**

For each repo in scope (single-repo arg, or each candidate in multi-repo mode), `cd` into the repo and capture:

```
git fetch origin                                                        # ensure refs fresh
git status --porcelain                                                  # working-tree state
git rev-parse --abbrev-ref HEAD                                         # current branch
# Base detection — see the resolution rule below                        # (replaces origin/HEAD)
git rev-list --count {BASE}..HEAD 2>/dev/null                           # ahead count
git rev-list --count HEAD..origin/{BASE}                                # behind count
git diff {BASE}..HEAD --stat                                            # diff stat
test -d .git/rebase-apply || test -d .git/rebase-merge                  # rebase in progress
test -f .git/MERGE_HEAD                                                 # merge in progress
test -f .git/CHERRY_PICK_HEAD                                           # cherry-pick in progress
test -f .git/BISECT_LOG                                                 # bisect in progress
git symbolic-ref HEAD                                                   # detached HEAD if non-zero
git diff --name-only --diff-filter=U                                    # unresolved conflicts
```

**Base branch resolution** — per the team Git Branching & Release Strategy (Confluence: `Git Branching & Release Strategy`, page id `327043186731`):

- **Feature PRs target `develop`.** The `develop` branch is the integration branch for sprint work.
- The skill only opens `feature/*` PRs (release/`/hotfix/*` are out of scope — see § NOT This Skill If).

Resolution algorithm:

1. Run `git rev-parse --verify origin/develop 2>/dev/null` — if it succeeds, `BASE = develop`.
2. Else fall back to `main` (or `master` if it's the only remote default) and emit a one-line warning:
   `Warning: origin/develop not found in {REPO_NAME} — falling back to base 'main'. Confirm the repo has adopted the team branching strategy.`
3. The resolved BASE is surfaced in the Step 0f.3 plan ("Base: develop" or "Base: main (no develop branch)") so the user sees it before any state change.

Do NOT use `git rev-parse --abbrev-ref origin/HEAD` — that points at the repo's default branch, which is usually `main` and would route feature PRs into `main` against the team strategy.

**Detect ticket commits across the whole repo** (used by Step 0e classification and Flow C):

```
TICKET_COMMITS=$(git log --all --grep="{TICKET_KEY}" --no-merges \
                   --not origin/{BASE} --reverse --pretty=%H)
```

Save the list (chronological order, oldest first). Save in particular: count, sha set, and the branch(es) where they currently live. These feed Step 0e (state classification) and Flow C (cherry-pick rescue).

---

## Step 0e: Detect Git State

Classify the current state into exactly one of six buckets. The classification decides whether prep runs (Step 0f), and which flow.

Read state from the facts already captured in **Step 0d's per-repo prep block** (working-tree state, current branch, ahead count, in-progress rebase/merge/cherry-pick/bisect markers, detached-HEAD check, and unresolved-conflict check) plus the `TICKET_COMMITS` list from Step 0d. No new commands are needed here — Step 0d's capture already produced every signal the classification below uses; base is resolved per Step 0d's "Base branch resolution" rule (develop preferred, main fallback).

Classify (mutually exclusive — top-most matching row wins):

| State | Conditions | Action |
|-------|-----------|--------|
| **Refuse: dangerous git state** | Detached HEAD, in-progress rebase / merge / cherry-pick / bisect, OR unresolved conflicts | Exit, see § Refuse states below |
| **Refuse: no ticket commits anywhere** | `TICKET_COMMITS` (from Step 0d) is empty | Exit, see § Refuse states below |
| **Already prepped** | On non-base branch + ≥1 commit ahead + clean tree + EVERY non-merge commit in `{BASE}..HEAD` references `{TICKET_KEY}` + no in-progress git op | Skip Step 0f, go to Step 1 |
| **Flow C — polluted ticket branch** | `TICKET_COMMITS` is non-empty AND (current branch is non-base AND has ticket commits + cross-ticket commits in `{BASE}..HEAD`, OR working tree is dirty with files outside the ticket commits' file set, OR ticket commits live on a different branch from current) | Step 0f — Flow C |
| **Flow A — rescue** | On `main` or `develop` + non-empty `git status --porcelain` | Step 0f — Flow A |
| **Flow B — fresh** | On `main` or `develop` + clean tree + no in-progress git op | Step 0f — Flow B |

Flow C is the default catch-all for the common "user has been working on this ticket, committed some of it, has unrelated churn in the tree" case. It cherry-picks the ticket commits onto a clean branch off base, leaving everything else stashed. The previous "Refuse: dirty feature branch" state is gone — Flow C handles it when ticket commits exist, and "Refuse: no ticket commits anywhere" handles it when they don't.

### Refuse states

**No ticket commits anywhere** — print and exit:
```
No commits matching {TICKET_KEY} were found on any branch in this repo (search:
git log --all --grep="{TICKET_KEY}" --no-merges --not origin/{BASE}).

Either:
  - Commit your work with the ticket key in the message (e.g. 'feat({TICKET_KEY}): ...'), then re-run /create-pr
  - Or verify you are in the right repo for this ticket
```

**Dangerous git state** — print and exit, substituting `{state name}` with the detected state (one of: `rebase`, `rebase-merge`, `merge`, `cherry-pick`, `bisect`, `detached HEAD`, `unresolved conflicts`):
```
Repo is in a dangerous git state: {state name}.
PR creation halted to avoid corrupting in-progress work.

Resolve the in-progress operation:
  - rebase: git rebase --continue OR git rebase --abort
  - merge:  git merge --abort
  - cherry-pick: git cherry-pick --abort
  - bisect: git bisect reset
  - detached HEAD: git switch <branch>

Then re-run /create-pr.
```

For full operator detail, see [references/prep-flows.md](references/prep-flows.md).

---

## Step 0f: Run Prep Flow (Flow A, Flow B, or Flow C)

Skip this step entirely if Step 0e classified as **Already prepped** — proceed directly to Step 1.

**Step 0f.1: Resolve the new branch name.**

**Prefix** — `feature/` for every sprint-level ticket. The team Git Branching & Release Strategy (Confluence page id `327043186731`) defines `feature/*` as the only branch type for in-sprint work (whether the Jira issuetype is Bug, Defect, Story, Task, Sub-task, or Epic). Bug fixes during a sprint are still sprint work, not hotfixes.

| Branch type (Confluence) | Used by this skill? | Prefix |
|---|---|---|
| `feature/*` | YES — every sprint-level ticket | `feature/` |
| `release/*` | NO — out of scope (manual semver flow) | n/a |
| `hotfix/*` | NO — out of scope (manual semver flow from a release tag) | n/a |

Fetch the Jira ticket via Atlassian MCP and cache `issuetype.name` — Step 1f (commit type) and Step 4 (title generation) reuse it. If the Atlassian MCP is unavailable, continue with `feature/` and print: `Note: Jira issue type not fetched — branch prefix defaults to feature/`.

**Description** — first match wins:

1. `tickets/{TICKET_KEY}/spec.md` → first `# ` (H1) heading after any front matter
2. `tickets/{TICKET_KEY}/rca.md` → first `# ` (H1) heading
3. Jira ticket Summary field
4. Ask user: `Branch description (kebab-case, ~50 chars):`

Transform: lowercase → replace non-alphanumeric runs with single hyphen → strip leading/trailing hyphens → truncate at last word boundary if total branch length would exceed 60 chars.

Final shape: `feature/{TICKET_KEY}-{kebab-description}`

Example: `feature/GEN-2759-template-filename-mismatch`

**Step 0f.2: Pre-check for local branch collision.**

```
git rev-parse --verify {NEW_BRANCH} 2>/dev/null
```

If exit code is 0 (the branch exists), do NOT refuse outright — pick a safe suffix and proceed:

1. Try `{NEW_BRANCH}-pr` (the suffix `-pr` signals "this is the clean cherry-pick branch for the PR").
2. If `{NEW_BRANCH}-pr` also collides, try `{NEW_BRANCH}-pr-2`, then `-pr-3`, etc.
3. Surface the chosen name to the user as part of Step 0f.3's plan:
   > `Branch '{ORIGINAL_NAME}' already exists locally — using '{NEW_BRANCH}' for the clean PR branch.`

This replaces the previous refusal behavior. The existing local branch is left untouched and the user can clean it up later. For Flow C in particular, the original local branch (the polluted one) is usually what the user has been working on — preserving it is correct.

**Step 0f.3: Show the plan and ask for confirmation.**

The per-flow operation sequences live in `references/prep-flows.md` (§§ Flow A / Flow B / Flow C — operations). Read them once and use them to populate the `Will run:` block below.

Show the plan **once**, substituting the operations for the matched flow:

```
Detected: {Flow A — rescue from base | Flow B — fresh start | Flow C — polluted ticket branch}
Base:     {develop | main (no develop branch — confirm intent)}
Branch:   {NEW_BRANCH}  (issuetype={JIRA_ISSUETYPE}, source={spec.md|rca.md|Jira summary})
Ticket commits: {N} to cherry-pick   ← Flow C only
  - {sha-short} {first line of commit subject}
  - {sha-short} {first line of commit subject}

Will run:
  {operations for matched flow — from prep-flows.md}

  {Flow C only:} The stash from step 2 is NOT auto-popped. Your dirty out-of-scope files stay safe in stash@{0} — pop or drop when you're ready.

Proceed? (yes / edit-branch / no)
```

- **yes** → run all operations sequentially (Step 0f.4)
- **edit-branch** → prompt `New branch name:`, validate against `^feature/(GEN|FIR|IVC|PARK)-\d+(-[a-z0-9-]+)?$`. If valid, replace and re-show the plan. If invalid, print the regex and re-prompt.
- **no** → exit cleanly. No state changes have been made (the plan was shown but not executed).

**Step 0f.4: Execute the prep operations.**

Run each command sequentially. Surface output of each to the user. **Stop immediately on the first non-zero exit code** — do not retry, do not strip flags, do not auto-rollback. (Rule 18 / Rule 19.)

Conflict gates are documented in `references/prep-flows.md`:
- Flow A `git stash pop` produced conflicts → § Conflict gate (Flow A only)
- Flow C cherry-pick produced conflicts → § Cherry-pick conflict gate (Flow C only)

Both gates wait for user `continue` or `abort` input and never auto-rollback. Stash policy across flows is also in prep-flows.md per-flow (Flow A pops, Flow C never auto-pops).

---

## Step 1: Code Review against Lessons Corpus

This step uses the `code-lesson` MCP to fetch the team's coding lessons relevant to the changed files, then walks the diff against them and offers fixes.

**Step 1a: Determine the stack.**

Read repo metadata to identify the stack:
- `package.json` → Node/TS/JS/Angular/React/NestJS detection from dependencies
- `tsconfig.json` → TypeScript
- File extensions in the diff → `.ts`, `.tsx`, `.js`, `.html`, `.scss`, `.go`, etc.

Map to the stack identifier the corpus uses (e.g. `angular-typescript`, `nestjs-typescript`, `node-typescript`).

**Step 1b: Fetch relevant lessons.**

```
mcp__code-lesson__get_lessons_for_stack(
  stack: "{STACK_ID}",
  severity: "high"        // start with high+critical to keep noise low
)
```

If the stack returns 0 lessons, retry with `severity: "medium"`. If still 0, skip this step and emit info: `No lessons found for stack {STACK_ID} — review skipped`.

**Step 1c: Open-comments check (optional but recommended).**

If the user has a manager-hub `pullRequestId` (CUID, NOT the GitHub PR number) for an existing PR being updated, call:
```
mcp__code-lesson__get_open_comments(pullRequestId: "<CUID>")
```
to avoid re-flagging findings already raised on the PR. For brand-new PRs, skip.

**Step 1d: Walk the diff.**

For each lesson returned, check whether the diff violates it. Build a findings list:

```
| # | File:Line | Lesson | Severity | Suggested fix |
|---|-----------|--------|----------|---------------|
| 1 | src/forms/FormController.ts:42 | Avoid `any` in public APIs | high | Use the FormPayload interface |
```

If 0 findings → continue to Step 2.

**Step 1e: Offer fixes interactively.**

For each finding, ask:
```
Finding {N}/{TOTAL} ({severity}): {file}:{line}
Lesson: {lesson title}
Why: {one-line summary}

Suggested fix:
{before/after diff}

Apply this fix? (yes / no / show-more)
```

- **yes** → use Edit to apply, mark as resolved
- **no** → mark as deferred (will appear in Step 5's confirmation summary)
- **show-more** → print the full lesson body, then re-ask

**Step 1f: Commit fixes.**

Before staging, **filter out forbidden files** (Rules 12–13). If any of the following appear in your changed-files list, do NOT auto-stage them — surface to the user and require manual handling:

- `.github/workflows/**`, `.gitlab-ci.yml`, `azure-pipelines.yml`, `.circleci/**`, `bitbucket-pipelines.yml`
- `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `Gemfile.lock`, `poetry.lock`, `go.sum`, `Cargo.lock`
- `.env`, `.env.*` (except `.env.example`), `firebase-debug.log`, anything matching `**/secrets/**`

If any fixes were applied to allowed files, commit in the team's Conventional-Commits-with-scope format. **Subject only — no `-m "{body}"` second argument, no auto-generated bullet list.**

```
git add <allowed changed files>
git commit -m "{TYPE}({TICKET_KEY}): {short developer-voice description of WHAT changed}"
```

Where `{TYPE}` matches the same logic as the branch prefix (Step 0f.1):

| Jira `issuetype.name` | Commit type |
|------------------------|-------------|
| `Bug`, `Defect` | `fix` |
| Anything else (Story, Task, Sub-task, Epic) | `feat` |
| Jira fetch failed | `feat` (fallback) |

**Subject rules — these are absolute:**

1. **Describe WHAT changed, not WHY it changed.** The reader of `git log` cares about the code delta, not the source of the feedback. "tighten country routing perf and input validation" tells them what to expect in the diff. "address review feedback on country routing" tells them nothing they couldn't infer from the PR linkage.
2. **No boilerplate meta-phrases.** Forbidden: `address review feedback`, `apply review fixes`, `apply review comments`, `code review fixes`, `cr fixes`, `address comments`, `respond to review`, `review fixes`. These signal an AI/bot author — a developer who knows their codebase writes what they did.
3. **No internal review-tool vocab.** Forbidden: `lesson finding(s)`, `lesson-finding`, `AI review`, `F1/F2/F3` identifiers, manager-hub PR IDs, MCP names. Output Guardian (`.claude/rules/output-guardian.md`) applies to commits the same as any other artifact.
4. **No body unless the user explicitly requests one.** No `-m "{body}"` second flag. No bullet list of findings. The PR's diff and the PR's review thread already carry the per-finding detail; the commit subject is for `git log` skimmability.
5. **Subject is ≤72 chars where possible.** If the change spans many small areas, name the dominant theme rather than enumerating all of them.

Good: `feat(GEN-1945): tighten country routing perf and input validation`
Good: `fix(GEN-2759): tighten template filename validation`
Good: `feat(GEN-1303): mortuary record popup wiring`
Bad:  `feat(GEN-1945): address review feedback on country routing` (meta-phrase, says nothing about the code)
Bad:  `review: address 5 lesson finding(s) for GEN-1945` (internal review-tool vocab)
Bad:  `chore(GEN-1945): apply AI review fixes` (mentions AI tooling + meta-phrase)

The commit message MUST NOT include any AI/automation attribution (`Co-Authored-By: Claude`, `🤖 Generated with Claude Code`, MCP names, etc.) — Rule 9.

Use ONE commit for all review fixes — keeps history readable. Do NOT amend the previous commit.

If 0 fixes applied (all deferred or 0 findings) → no commit, continue.

Re-capture git facts (Step 0d) since the commit count changed.

---

## Step 2: Pre-flight Checker

Once Step 1 completes (with or without fixes), validate the PR inputs via the pre-flight checker subagent BEFORE pushing.

1. Read `./checker-prompt.md` from this skill folder.
2. Dispatch a `pipeline-checker` subagent (`.claude/agents/pipeline-checker.md`) with:
   - The full prompt from `checker-prompt.md`
   - Ticket key, repo path, repo name, current branch, base branch, drafted title and body (built in Step 4)
   - Pre-computed git facts (output of `git status --porcelain`, `git rev-list --count`, `git diff {BASE}..HEAD --stat`, first 200 lines of `git diff {BASE}..HEAD`, `gh auth status`)
   - **The full file list** from `git diff --name-only {BASE}..HEAD` (used by P24 for spec-vs-diff cross-check — the 200-line truncation of the full diff isn't enough to extract the complete changed-file set)
   - **The contents of `tickets/{TICKET_KEY}/spec.md`** if it exists (also for P24). If absent, note it in the dispatch prompt; P24 will skip.
   - Result of `gh pr list --head {BRANCH} --state open --json number,title --limit 1` (for P11)
3. Parse the JSON result block: `{ verdict, ticket_key, repo, branch, summary, gaps[] }`.
4. Branch on verdict:
   - **FAIL** → print every blocker, exit. Do NOT push. Do NOT create PR.
   - **WARN** → print every warning, ask `Proceed anyway? (yes/no)`. If `no` → exit. If `yes` → continue, record acknowledged warning IDs (e.g. `P9, P10`) for the Step 7 summary.
   - **PASS** → continue.

Format each gap as:
```
[<rule>] <issue>
  Resolve: <suggested_fix>
  Evidence: <evidence>     ← only if present
```

If the checker dispatch fails or returns malformed JSON: print `Pre-flight could not run: <reason>. Without pre-flight, no automated input validation.` Then ask `Proceed without pre-flight? (yes/no)`. Capture `Pre-flight: SKIPPED (dispatch failure: <reason>)` for Step 7.

---

## Step 3: Push the Branch

Push the branch to `origin` (which on `ivc.ghe.com` resolves correctly via the repo's git config).

```
git push -u origin {CURRENT_BRANCH}
```

Forbidden flags (the checker P13 enforces these as blockers — repeat the rule here so the agent never tries them):
- NEVER `--force` or `--force-with-lease` unless the user has explicitly typed those exact flags in this turn
- NEVER `--no-verify` (skips pre-push hooks like commit signing or lint)
- If the push is rejected (non-fast-forward): stop. Tell the user `Push rejected — branch is not fast-forward. Investigate the conflict before re-running /create-pr`

If the branch is already on `origin` (output indicates `Everything up-to-date`), continue silently.

---

## Step 4: Generate Title and Body

Read `./references/pr-body-template.md` for the canonical format.

**Title format:** `KMS-{TICKET_KEY}: {short imperative description}`

The `KMS-` prefix is the team convention — always present, regardless of ticket project (`GEN`, `FIR`, `IVC`, `PARK`). The separator after the ticket key is `: ` (colon space).

- Build a one-line description from the diff stat:
  - If 1–3 files changed: name the primary feature area + the verb (e.g. "document two-contact create flow and new client fields")
  - If many files changed: state the high-level change (e.g. "refactor estimate flow to support partial annotations")
- Imperative description, no trailing period; no leading Conventional-Commits verb (`feat:` / `fix:`) — the only colon is the one right after the ticket key
- Keep under 100 chars when possible

Example: `KMS-FIR-2034: document two-contact create flow and new client fields`

**Body:**

Default (code-only or no migration plan):
```
TICKET: https://invocarecompass.atlassian.net/browse/{TICKET_KEY}
```

With Data Migration plan (config / mixed fix — detect by checking `tickets/{TICKET_KEY}/session-log.md` for any successful Firebase write entry):
```
TICKET: https://invocarecompass.atlassian.net/browse/{TICKET_KEY}
- [x]  Data Migration plan on UAT: Technical Approach
```

Pre-check the box (`[x]`) — the existence of session-log.md asserts a plan exists. Use `[ ]` only if the user explicitly says the plan is pending.

Do NOT add Summary, Test Plan, Screenshots, or any other section. The team's sample PRs are minimal. Match that.

---

## Step 5: Confirm with the User

Show the drafted PR before creating it:

```
About to open PR for {TICKET_KEY}:

Repo:    {REPO_NAME}
Base:    {BASE}
Head:    {CURRENT_BRANCH}
Commits: {N} ahead of {BASE}
Files:   {N} changed (+{ADDED} −{REMOVED})

Title:
{TITLE}

Body:
{BODY}

{IF deferred review findings:}
⚠️  {N} review finding(s) deferred — will be visible in the PR diff for reviewer attention

{IF acknowledged pre-flight warnings:}
⚠️  Pre-flight warnings acknowledged: {P9, P10, ...}

Proceed? (yes / edit / no)
```

- **yes** → continue to Step 6
- **edit** → ask which: `(title / body / both)`. Accept user-provided text, replace, re-show this confirmation
- **no** → exit. Branch is pushed but no PR was created. User can run `/create-pr` again later

---

## Step 6: Create the PR

```
GH_HOST=ivc.ghe.com gh pr create \
  --repo FireHawk/{REPO_NAME} \
  --base {BASE} \
  --head {CURRENT_BRANCH} \
  --title "{TITLE}" \
  --body "$(cat <<'EOF'
{BODY}
EOF
)"
```

Use a HEREDOC for the body to preserve formatting and avoid quote-escaping bugs.

**Forbidden flags on this command** (Rule 14):
- NEVER `--draft`
- NEVER `--auto-merge` or `--auto`
- NEVER `--reviewer` (Rule 6 — reviewers are manual)
- NEVER `--label` unless the user has typed the exact label in this turn

If `gh pr create` fails:
- `pull request already exists` → fetch and report the existing URL via `gh pr view --head {CURRENT_BRANCH} --json url`
- `unauthorized` / `403` → tell the user to refresh `gh auth status --hostname ivc.ghe.com`
- Other failures → report the error verbatim and stop. Do NOT retry, do NOT remove flags and re-attempt — Rule 18.

---

## Step 7: Summarize

**Single-repo invocation** — one card:
```
✓ PR created for {TICKET_KEY}

Repo:    {REPO_NAME}
URL:     {PR_URL}
Title:   {TITLE}
Flow:    {Already prepped | Flow A | Flow B | Flow C with N cherry-picks}
Pre-flight: PASS | WARN (acknowledged: P9, P10) | SKIPPED ({reason})

{IF deferred findings:}
Deferred review findings: {N} (visible in the diff for reviewer attention)
- {file:line} — {lesson title}

{IF Flow C and stash retained:}
Stashed out-of-scope work: stash@{0} ("create-pr-prep-{TICKET_KEY}"). `git stash pop` to restore or `git stash drop` to discard.
```

**Multi-repo invocation** — one combined card listing each PR:
```
✓ Opened {N} PR(s) for {TICKET_KEY}

| Repo                | PR URL                                                | Flow      | Pre-flight |
|---------------------|-------------------------------------------------------|-----------|------------|
| FCRM-Web            | https://ivc.ghe.com/FireHawk/FCRM-Web/pull/43         | Flow C (1)| PASS       |
| document-templates  | https://ivc.ghe.com/FireHawk/document-templates/pull/7| Flow C (1)| PASS       |

{IF any deferred findings:}
Deferred review findings across all PRs: {N} (visible in each diff)

{IF any Flow C stashes retained:}
Stashed out-of-scope work in {M} repo(s). Recover per-repo with `git stash pop` or `git stash drop`.

{IF any candidate repo was skipped on user request:}
Skipped (not selected): {REPO_LIST}
```

---

## Hotfix-to-Main Workflow (Promote to UAT)

Runs **instead of** Steps 0a–7 when the invocation specifies hotfix mode (`hotfix`, `to main`, `to uat`, `to UAT`, or `--hotfix`). It cherry-picks already-reviewed commits from `origin/develop` onto a fresh `hotfix/*` branch cut from `origin/main`, then opens one PR per repo targeting `main` (steps H0–H5: inherited rules, per-repo preflight, branch naming, cherry-pick + hygiene + push + PR, aggregate summary, anti-patterns). Step 1 (lessons review) is skipped in hotfix mode; Step 2 (pre-flight checker) still runs. Use it when the ticket is already merged to `develop` and must land on `main` ahead of the normal release cut.

**For the hotfix-to-main flow, follow [references/hotfix-flow.md](references/hotfix-flow.md).** Every step and rule lives there verbatim.

---

## Rules

1. **Never push to `main` or `master`.** P2 enforces — if the current branch is the base, refuse.
2. **Never use `--force`, `--force-with-lease`, or `--no-verify`** unless the user has typed those exact flags in this turn. P13 enforces.
3. **Never commit secrets.** P6 scans the diff. If matched, stop and surface — never proceed.
4. **Body MUST start with `TICKET: <jira-url>`** (uppercase `TICKET:`) — team convention from sample PRs.
5. **Title MUST follow `KMS-{TICKET_KEY}: <description>`** — the `KMS-` prefix is the team convention and the separator after the ticket key is `: ` (colon space); do not omit the prefix.
6. **Reviewers are NOT auto-assigned** — the user picks them in the PR UI manually.
7. **Code review fixes go in ONE subject-only commit.** Full format, type mapping, absolute prohibitions, and bad examples are in Step 1f. Do not amend the prior commit.
8. **No automated Jira link-back** — this skill creates the PR only. If the user wants to comment on Jira with the PR URL, they run `/ticket-comment {TICKET_KEY}` separately.
9. **Never include AI/automation attribution** in commits or PR body — no `Co-Authored-By: Claude`, no `🤖 Generated with Claude Code`, no MCP names, no tool names. Output Guardian rules apply to git commits too. P14 enforces.
10. **Never auto-close upstream issues.** No `Closes #N`, `Fixes #N`, `Resolves #N` keywords in the PR body — humans close issues manually after review. P15 enforces.
11. **Refuse on a dangerous git state.** Detached HEAD, in-progress rebase / merge / cherry-pick / bisect, or unresolved conflicts → stop. P16 enforces.
12. **Never modify CI configuration during review fixes.** Files under `.github/workflows/`, `.gitlab-ci.yml`, `azure-pipelines.yml`, or any CI config are off-limits in Step 1's auto-fix path. If a review finding targets one, surface it but do NOT auto-apply. P17 enforces.
13. **Never modify lock files during review fixes.** `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `Gemfile.lock`, `poetry.lock`, `go.sum`, `Cargo.lock` — Step 1 must not touch these as part of "fix a finding." If a fix would change a lock file, surface it and require a separate manual step. P18 enforces.
14. **Never use `--draft` or `--auto-merge` / `--auto`** when calling `gh pr create` unless the user explicitly types those exact words in this turn. P19 enforces.
15. **One PR per repo, multi-repo iteration permitted per invocation.** When a repo name is passed (`/create-pr GEN-XXXX FCRM-Web`), exactly one PR is created for that repo. When the repo name is omitted (`/create-pr GEN-XXXX`), the skill discovers every repo under `$INVOCARE_ROOT` with commits matching the ticket key (Step 0c) and — with explicit user confirmation — iterates through them, opening one PR per repo and emitting a combined summary at the end. Never aggregate multiple repos into a single PR.
16. **Never delete the branch after PR creation.** No `git push origin --delete`, no `git branch -D`. The team merges via the PR UI; deleting the branch from the skill would orphan in-flight reviews.
17. **Block only when local-only config files would land in the diff.** `.env`, `.env.*` (except `.env.example`), `firebase-debug.log`, `*.local.json` outside known patterns: if any of these are STAGED or appear in `git diff {BASE}..HEAD --name-only`, refuse. If they exist only in the working tree as untracked/unignored AND are not in the PR diff, surface a one-line warning and let Flow C's stash isolate them. P20 enforces the diff-scope check; the working-tree-only case is handled by the override path in Rule 24.
18. **Stop on ANY git or `gh` error.** Never retry, never escalate (e.g. drop a flag and retry without it), never silently continue. Surface the error verbatim and let the user decide.
19. **Prep is a single user-confirmation gate, executed sequentially.** Show the full plan once, ask once, run sequentially. Stop on any failure. Never retry. Never auto-rollback after partial execution — surface the manual recovery recipe and exit.
20. **Apply `.claude/rules/git-safety.md`.** Universal git rules — no destructive flags, no rewriting pushed commits, no diff cruft, refuse on dangerous git states, etc. Checker rules P25 and P28 enforce the create-pr-relevant subset at PR-creation time. The shared rule covers the broader baseline.
21. **At least one commit on the branch must reference the ticket key.** Squash-merges may collapse individual commit messages — at least one source commit needs `(GEN|FIR|IVC|PARK)-\d+` in its message so the branch is greppable post-merge. PR-specific (only relevant when opening a PR). P26 enforces.
22. **Refuse if the branch is too far behind base.** If `git rev-list --count HEAD..{BASE}` exceeds 50, the branch is stale and a merge will likely conflict. Rebase against current base before re-running. PR-specific. P27 enforces.
23. **Apply `.claude/rules/agents-safety.md`.** Universal subagent rules — inherit Output Guardian and Secrets Safety, read-only by default, verify don't trust, structured output, escalate failures rather than auto-retry. The pre-flight checker dispatched in Step 2 is the only subagent this skill currently uses; the rules apply to any future subagent.

24. **Override Semantics — which rules the user can wave through, which are absolute.** The user CANNOT override the following under any circumstance: P2 (push to base), P6 (secrets in diff), P14 (AI/automation attribution), P15 (issue-closing keywords), P16 (dangerous git state), P28 (build artifacts in diff), Rule 1 (push to base), Rule 3 (commit secrets), Rule 9 (attribution), Rule 10 (closing keywords), Rule 11 (dangerous state). Attempting to is itself a violation. The user CAN override the following by explicitly typing `yes` (single token, single turn) after the skill surfaces the gap: P9 (branch name lacks ticket key — convention only), P12 (migration-checkbox state mismatch), P20 in its untracked-only form (Rule 17, working tree contains an unignored `.env` that is NOT in the PR diff), P26 (no commit message references ticket key — fixed by P10's title enforcement), P27 (branch >50 commits behind base — heuristic), and the new P29 (cross-ticket commits on branch — usually auto-resolved by Flow C). Forbidden-flag rules (P13, P19) are NOT user-overridable mid-skill; the user can only "opt in" by typing the exact forbidden flag in their original request, which the skill then echoes back for confirmation.

25. **Apply the team Git Branching & Release Strategy.** Source: Confluence page `Git Branching & Release Strategy` (page id `327043186731`). This skill operationalizes the strategy as follows:
    - **Branch prefix is `feature/`** for every sprint-level ticket (Bug, Defect, Story, Task, Sub-task, Epic). Sprint-level bug fixes are still `feature/*` — they are not `hotfix/*`.
    - **Branch name shape:** `feature/{TICKET_KEY}-{kebab-description}` (description suffix is a team-internal enhancement on top of Confluence's `feature/{TicketID}` minimum).
    - **Branch-name validation regex:** `^feature/(GEN|FIR|IVC|PARK)-\d+(-[a-z0-9-]+)?$` — enforced by Step 0f.3 `edit-branch` validation and by P9 in the checker.
    - **Base branch is `develop`.** Feature PRs target `develop`, never `main`. The skill resolves base by checking `origin/develop` first (Step 0d). If `origin/develop` does not exist, the skill falls back to `main` and emits a one-line warning — confirm intent before pushing.
    - **`release/*` and `hotfix/*` are out of scope** for this skill (see § NOT This Skill If). Those follow the manual semver flow per the Confluence doc: `release/{semver}` cut from `develop` and targeting `main` + back-merge to `develop`; `hotfix/{semver}` cut from a release tag on `main` with the same back-merge.
    - **Tags are produced on `main` only** (per the Confluence doc). This skill never tags — tagging is a separate release operation.
    - **Stable-branch merges require Tech Lead approval** (per the Confluence doc). This skill never opens PRs into `main` for feature work; the approval gate applies to the release PR, which is opened manually.

---

## Guardrails (single-page summary)

| Layer | Guardrail | Where enforced |
|-------|-----------|----------------|
| **Branch state** | Refuse on `main`/`master`, detached HEAD, in-progress rebase/merge/cherry-pick | P2, P16 |
| **Branching strategy** | Feature PRs target `develop`; prefix is `feature/`; `release/*` and `hotfix/*` out of scope | Rule 25, Step 0d, Step 0f.1, P8 |
| **Working tree** | Refuse if local-only configs are STAGED or in diff; warn-only when present untracked outside diff (Flow C stashes them) | P20 (refined), Rule 17 |
| **Diff hygiene** | No secrets, no PII, no large binary blobs, no AI attribution | P6, P14 |
| **Auto-fix scope** | Never touch CI configs or lock files during review auto-fix | P17, P18, Step 1f |
| **Push** | No `--force`, no `--no-verify`, no force flags ever | P13, Step 3 |
| **PR creation** | No `--draft`, no `--auto-merge`, no `--auto` | P19, Step 6 |
| **PR body** | Must contain Jira URL, must NOT contain `Closes #`, `Fixes #`, `Resolves #` | P7, P15 |
| **PR title** | Must match `KMS-{TICKET_KEY}: <description>` | P10 |
| **Branch lifecycle** | Never delete the branch from this skill | Rule 16 |
| **Multi-repo** | One PR per repo; with no repo arg, discover candidates and iterate after user confirmation; never aggregate repos into one PR | Rule 15 |
| **Polluted branches** | Flow C cherry-picks ticket commits onto a clean branch off base; cross-ticket commits warned by P29 (sanity check) | Step 0f / Flow C, P29 |
| **Overrides** | Absolute rules unwaivable; overridable rules only after explicit `yes` | Rule 24 |
| **Reviewers** | Never auto-assign | Rule 6 |
| **Jira link-back** | Never auto-comment on Jira from this skill | Rule 8 |
| **Errors** | Stop on any git/gh failure; never retry, never escalate | Rule 18 |
| **Git history** | No amended/rebased commits that were already pushed | P25 |
| **Audit trail** | At least one commit must reference the ticket key | P26 |
| **Branch freshness** | Branch must be ≤50 commits behind base | P27 |
| **Diff cleanliness** | No build artifacts, OS files, editor cruft | P28 |
| **Diff completeness** | Spec-referenced files must appear in diff (warning) | P24 |
| **Subagents** | Read-only, inherit Output Guardian + Secrets Safety, return structured JSON, escalate failures | Rule 23 → `.claude/rules/agents-safety.md` (A1–A5) |

---

## Quality Bar

A run is complete when every phase below was performed AND the constraint set it cites was honored. The constraint *content* is NOT restated here — each item points at its authoritative location (a Step, a Rule, a checker P-rule, or the § Guardrails row). To audit a constraint, follow the reference.

**Resolution & discovery (Step 0)**
- [ ] Repo path resolved under `$INVOCARE_ROOT` and confirmed to exist (Step 0b)
- [ ] Ticket key extracted from arg / branch / in-flight ticket folder; arg-vs-branch mismatch warned (Step 0a)
- [ ] Multi-repo discovery ran when no repo arg was given — candidate list shown, user confirmed `yes` / `pick` / `no` (Step 0c); one PR per repo, never aggregated (Rule 15)
- [ ] Ticket commits detected per repo via the Step 0d `git log --all --grep` command; ≥1 commit references the ticket key (P26)

**Git-state classification & prep (Steps 0e–0f)**
- [ ] State classified into exactly one of: Already prepped / Flow A / Flow B / Flow C / Refuse-no-ticket-commits / Refuse-dangerous (Step 0e); not a dangerous git state (Rule 11 / P16)
- [ ] Branch name = `feature/{TICKET_KEY}-{kebab-description}`, prefix per Rule 25; base resolved `develop`-then-`main`-with-warning per Step 0d; `release/*` / `hotfix/*` out of scope (Rule 25, NOT This Skill If)
- [ ] Local branch collision handled by safe suffix, never refused (Step 0f.2); prep plan shown once before any state change, user confirmed (Step 0f.3)
- [ ] Prep ran sequentially with no auto-rollback / no retry after a failure (Rule 18 / Rule 19); Flow C cherry-picks chronological with conflicts cleared, stash retained not popped (Step 0f.4); Flow A stash-pop conflicts cleared via the gate (Step 0f.5)

**Lessons review & commit (Step 1)**
- [ ] Stack identified; lessons corpus queried at severity high+ (medium if 0); review skipped only when corpus has nothing (Steps 1a–1b)
- [ ] Each finding shown with file:line, severity, before/after diff (Step 1d–1e)
- [ ] Review fixes committed as ONE subject-only Conventional-Commits-with-scope commit per Step 1f (Rule 7 — WHAT not WHY, no meta-phrases, no body, not amended), or no commit if 0 fixes; commit did NOT touch CI configs or lock files (Rule 12 / P17, Rule 13 / P18); no AI/automation attribution (Rule 9 / P14)

**Pre-flight, push & PR (Steps 2–6)**
- [ ] Pre-flight checker ran — verdict captured (PASS / WARN with acknowledged IDs / SKIPPED with reason) (Step 2)
- [ ] Diff scanned for secret patterns (Rule 3 / P6); no build artifacts / OS files / editor cruft (P28); spec-referenced files cross-checked against diff (P24); no local-only config files staged or in diff (Rule 17 / P20)
- [ ] Branch pushed with `-u`, no forbidden push flags (Rule 2 / P13); no amended/rebased pushed commits (P25); branch ≤50 commits behind base (P27)
- [ ] Title = `KMS-{TICKET_KEY}: <description>` (Rule 5 / P10); body starts with the Jira `TICKET:` URL (Rule 4 / P7), migration checkbox only when session-log.md shows config writes, no issue-closing keywords (Rule 10 / P15)
- [ ] User confirmed title and body before `gh pr create` (Step 5); `gh pr create` ran without `--draft` / `--auto-merge` / `--auto` / `--reviewer` / `--label` unless user opted in (Rule 14 / P19); branch NOT deleted after creation (Rule 16)

**Cross-cutting**
- [ ] PR URL surfaced in the summary (Step 7)
- [ ] Override semantics honored — absolute rules never waived, overridable rules only after explicit user `yes` (Rule 24)
- [ ] Output Guardian + Secrets Safety honored in every commit / output / PR artifact (Rule 9, opening safety notes)
- [ ] Subagent rules applied per `.claude/rules/agents-safety.md` (Rule 23 — A1–A5)

---

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Including a "Test Plan" section in the body | Team convention is minimal bodies — just the Jira link (and migration checkbox if applicable) |
| Auto-assigning reviewers | The user assigns manually in the PR UI |
| Force-pushing to recover from a rebase | Forbidden by P13 — user does this manually if needed |
| Generating a Conventional Commits-style title (`feat:`, `fix:`) | Team uses `KMS-{TICKET_KEY}: <description>` — no leading verbs before the description |
| Omitting the `KMS-` prefix from the title | The prefix is mandatory regardless of project (`GEN`, `FIR`, `IVC`, `PARK`) |
| Posting the PR URL to Jira from this skill | This skill only creates the PR. Run `/ticket-comment {TICKET_KEY}` separately if Jira needs the link |
| Refusing on a polluted feature branch | Don't refuse — Flow C is the rescue. Cherry-pick ticket commits onto a clean branch off base, stash the rest, push the new branch. |
| Refusing on an untracked `.env` not in the diff | Don't refuse outright. Surface a one-line warning; Flow C stashes it. Only refuse if `.env` is STAGED or in the PR diff. |
| Stashing then auto-popping in Flow C | Flow C never auto-pops. The stashed files are out-of-scope by definition; user pops manually when they want them back. |
| Refusing on a local branch name collision | Don't refuse. Auto-suffix `-pr`, `-pr-2`, … and surface the chosen name in the prep plan. |
| Reading individual `tickets/` ticket folders' commit messages instead of `git log --grep` | The git log is the audit trail. Ticket folders are planning artifacts and may not align with what was actually committed. |
| Targeting `main` for a feature PR | Per the team Git Branching & Release Strategy (Rule 25), feature PRs target `develop`. The skill resolves base via `origin/develop`, falling back to `main` only with a warning. |
| Using `feat/` or `fix/` as the branch prefix | Confluence-canonical prefix is `feature/` for all sprint-level work. Bug fixes during a sprint are `feature/`, not `fix/` and not `hotfix/`. `hotfix/*` is reserved for urgent prod fixes cut from a release tag on `main`. |
| Cutting a `release/*` or `hotfix/*` branch through `/create-pr` | Out of scope. Open those PRs manually per the Confluence doc — they target `main` with a back-merge to `develop` and follow semver naming. |

---

## Next step

After completing this skill, print the block below before ending. Substitute the actual ticket key for `{TICKET_KEY}` and one of the two forms based on single-vs-multi-repo invocation.

**Single-repo form:**
```
---
**Next step**

PR is open: {PR_URL}

Manual steps from here:
- Request reviewers in the PR UI
- Run /ticket-comment {TICKET_KEY} if you want the PR URL posted back to Jira
- Monitor CI; address review feedback as it comes in
- {IF Flow C stash retained:} Recover or drop the stashed out-of-scope files when convenient: `git stash list` then `pop` or `drop`
---
```

**Multi-repo form:**
```
---
**Next step**

{N} PR(s) open for {TICKET_KEY}:
- {REPO_1}: {PR_URL_1}
- {REPO_2}: {PR_URL_2}
{...}

Manual steps from here:
- Request reviewers in each PR UI (reviewers may differ across repos)
- Run /ticket-comment {TICKET_KEY} once — the comment can reference all PR URLs
- Monitor CI per-PR; address review feedback as it comes in
- {IF any Flow C stashes retained:} Per-repo: recover or drop stashed out-of-scope files when convenient
---
```
