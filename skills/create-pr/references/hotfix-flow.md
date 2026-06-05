# Hotfix-to-Main Workflow (Promote to UAT)

Runs **instead of** Steps 0a–7 of `SKILL.md` when the invocation specifies hotfix mode (`hotfix`, `to main`, `to uat`, `to UAT`, or `--hotfix`). Cherry-picks already-reviewed commits from `origin/develop` onto a fresh `hotfix/*` branch cut from `origin/main`, then opens one PR per repo targeting `main`.

**When this is the right tool:** the ticket is already on `develop` (PRs merged) and you need it on `main` ahead of the normal release cut — usually because UAT builds off `main`, or because the fix must reach production before the next release.

**When this is NOT the right tool:**
- The ticket isn't merged to `develop` yet → use the feature flow.
- You want to ship the entire current sprint to `main` → that's a `release/{semver}` PR, opened manually per the Confluence strategy.
- The fix is Firebase-config only with no code committed → use `/apply-fix {KEY} {env}` directly.

## H0: Inherited rules and guardrails

Every Rule under § Rules (1–25) and every row in § Guardrails of `SKILL.md` applies to this workflow, with these specific reaffirmations:

- **Rule 1 / P2** — never push to `main`. The PR targets `main`; the push goes to the hotfix branch.
- **Rules 2, 18, 19** — no destructive flags ever, stop on any git/gh error, never auto-retry.
- **Rule 9 / P14** — no AI/automation attribution in commits or PR body.
- **Rule 10 / P15** — no `Closes #N` / `Fixes #N` / `Resolves #N` keywords in the body.
- **Rule 11 / P16** — refuse on dangerous git state (detached HEAD, in-progress rebase/merge/cherry-pick, unresolved conflicts).
- **Rule 25** — base is `main` (the only mode where this is correct); branch shape is `hotfix/{TICKET_KEY}-{kebab-description}`.

## H1: Pre-flight across candidate repos

Resolve the ticket key (Step 0a) and repos (Step 0b's multi-repo discovery, but matching on `origin/develop` for ticket commits, since hotfix-mode source is develop not the local branch):

```
git -C "$BASE/$repo" log --grep="{TICKET_KEY}" --no-merges --reverse \
  --pretty=%H origin/develop --not origin/main
```

A repo is a **candidate** if this returns ≥1 SHA. For each candidate, capture:

- `gh auth status --hostname ivc.ghe.com` — must show authenticated
- `git remote get-url origin` — must point at `ivc.ghe.com:FireHawk/...`
- `git fetch origin`
- **Local `main` divergence check:** `git rev-list --left-right --count main...origin/main` — if local `main` has commits ahead of origin/main, surface them via `git log --oneline origin/main..main` and ask the user. **Default behavior is to ignore local `main` and branch from `origin/main` directly** — leave the local divergence alone.
- **Hotfix-already-on-main check:** `git log --oneline --grep="{TICKET_KEY}" origin/main` — if any matches, stop and report; the hotfix is already there.
- **Source SHAs to cherry-pick** (captured above): chronological list of non-merge commits on `origin/develop` not yet on `origin/main` whose messages reference the ticket key. **Never include the merge commit** itself — cherry-pick replays the original feature commits, not the develop merge.

Present the candidate list and the SHAs to be cherry-picked per repo. Ask the user `Proceed with all? (yes / pick / no)`. Same semantics as Step 0c.

## H2: Branch name

Per repo, derive `hotfix/{TICKET_KEY}-{kebab-description}`:

- Description source: same precedence as Step 0f.1 — spec.md H1 → rca.md H1 → Jira Summary → user prompt.
- Local branch collision → suffix `-pr`, `-pr-2`, … (Step 0f.2 rule).
- Surface the chosen name to the user before any state change.

## H3: Per-repo execution

Iterate repos sequentially. **After each repo, surface its PR URL and stash status to the user**; if the user invoked with multi-repo intent, ask whether to continue to the next repo (checkpoint between repos).

For each repo:

**H3a — Stash unrelated working-tree changes.**

```
git status --porcelain     # if non-empty
git stash push -u -m "create-pr-hotfix-prep-{TICKET_KEY}: env churn"
```

Surface the resulting `stash@{0}` ref to the user. The stash is **never auto-popped** by this workflow — the user controls recovery.

If a dangerous git state (Rule 11 / P16) is detected here, refuse and exit.

**H3b — Create hotfix branch off `origin/main`.**

```
git checkout -b hotfix/{TICKET_KEY}-{kebab} origin/main
```

Branching off the **remote** ref sidesteps any local `main` divergence detected in H1.

**H3c — Cherry-pick the captured SHAs chronologically.**

```
git cherry-pick {SHA1} {SHA2} ...
```

**Cherry-pick conflict gate:** if any cherry-pick exits non-zero with a conflict marker, STOP. Tell the user:

```
Cherry-pick conflict in {REPO} during {SHA}:
  {files-with-conflict-markers}

This workflow never auto-resolves conflicts. Resolve manually, then either:
  - continue: git cherry-pick --continue, then re-run /create-pr {KEY} hotfix --resume
  - abort: git cherry-pick --abort  (the hotfix branch will be empty; re-run later)
```

**H3d — Diff hygiene scan.**

```
git diff --name-only origin/main..HEAD
```

Scan output for the same forbidden patterns the feature flow's pre-flight checker enforces (P6 secrets, P17 CI configs, P18 lock files, P20 env files, P28 build artifacts). If ANY match, STOP with the matched filenames. Re-running requires the user to clean up first.

Then print `git diff --stat origin/main..HEAD` so the user sees scope.

**H3e — Push.**

```
git push -u origin hotfix/{TICKET_KEY}-{kebab}
```

Forbidden: `--force`, `--force-with-lease`, `--no-verify`. If push is rejected (non-fast-forward) → STOP, never retry.

**H3f — Open PR via `gh` with minimal body.**

```
GH_HOST=ivc.ghe.com gh pr create \
  --repo FireHawk/{REPO_NAME} \
  --base main \
  --head hotfix/{TICKET_KEY}-{kebab} \
  --title "KMS-{TICKET_KEY}: Hotfix - {short imperative description}" \
  --body "TICKET: https://invocarecompass.atlassian.net/browse/{TICKET_KEY}"
```

**Body MUST be exactly the single `TICKET:` line.** Do NOT include:
- Back-merge narrative or rationale
- "Hotfix promotion — cherry-picks from develop…" explanations
- "Requires Tech Lead approval" reminders (the strategy enforces this, not the PR body)
- Any other section, prose, or checklist

The minimal body matches the team's existing PR convention (Step 4) — the only difference between feature and hotfix PR bodies is the `Hotfix:` prefix in the **title**, not extra content in the **body**.

Forbidden `gh` flags (same as Step 6): no `--draft`, no `--auto-merge` / `--auto`, no `--reviewer`, no `--label` unless the user typed it.

## H4: Aggregate summary

After every repo completes (or the user halts mid-flow), print one combined card:

```
✓ Opened {N} hotfix PR(s) for {TICKET_KEY}

| Repo        | PR URL              | Source SHAs cherry-picked | Stash retained |
|-------------|---------------------|---------------------------|----------------|
| {REPO_NAME_1} | {PR_URL_1}        | {SHA1}, {SHA2}, ...       | stash@{0} (only if H3a stashed) |
| {REPO_NAME_2} | {PR_URL_2}        | {SHA}                     | —              |

Manual next steps:
- Request Tech Lead reviewer in each PR UI
- After both merge to main, open back-merge PR `main → develop` per the team branching strategy
  (content is a no-op since the diff is already on develop — the merge commit is for branch graph hygiene only)
- /ticket-comment {TICKET_KEY} if you want the PR URLs posted to Jira
- Pop or drop any retained stashes when convenient
```

## H5: Hotfix-specific anti-patterns

These reaffirm the gates above — if you catch yourself doing any of these, stop:

| Anti-pattern | What to do instead |
|---|---|
| Cherry-picking the develop merge commit (e.g. a `Merge pull request #N from …` commit object) | Cherry-pick the **original feature commits** from inside the merged branch. The `git log --grep --no-merges` filter in H1 already excludes merge commits. |
| Branching the hotfix off **local** `main` when it has diverged from origin/main | H3b branches off `origin/main` exactly to avoid this. Local divergence is a separate cleanup the user owns. |
| Writing a multi-paragraph PR body explaining what a hotfix is, why this one needs Tech Lead approval, what the back-merge plan is | The body is exactly one `TICKET:` line. The Confluence Git Branching & Release Strategy is the source of truth — not the PR body. |
| Auto-popping the prep stash after PR creation | Never auto-pop. The stash is the user's choice to recover. |
| Re-running Step 1 (lessons code review) on cherry-picked commits | Skip Step 1 in hotfix mode. The cherry-picked commits were already gated at the original PR (feature → develop) review — re-flagging would re-raise resolved issues. |
| Re-running Step 2 (pre-flight checker) on the hotfix branch | DO run the checker — generic PR-creation gates (P2, P6, P9, P10, P13, P14, P15, etc.) still apply. Only Step 1 (lessons review) is skipped in hotfix mode. |
| Letting the cherry-pick produce a diff that includes lock files, CI configs, env files, or build artifacts | H3d's hygiene scan stops the workflow before push. If a forbidden file appears, the user fixes the source commit on develop (separate work) — the hotfix doesn't get a "fix it as we go" exception. |
