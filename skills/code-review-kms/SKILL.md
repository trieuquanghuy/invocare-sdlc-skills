---
name: code-review-kms
description: "Drive the manager-hub AI code review on a pull request, end-to-end, stopping at three human gates. Use when someone asks to run the AI review on a PR, re-review a PR after fixes, get the review score up, or work through review findings before merging. Triggers on: run the AI review, code review PR 152, review this PR with manager-hub, re-review after my fixes, AI review before merge, review score below 7.5. Works from a plain repo checkout OR a git worktree — it detects which and adapts. Findings are produced locally and the server is written to exactly once, after you push."
argument-hint: "<PR number | manager-hub prId> [checkout-path] [branch] [base-ref]"
disable-model-invocation: true
---

# Code Review (manager-hub)

Drive the manager-hub code review workflow on a pull request, end-to-end, and STOP at its **three** human gates.
The fix-and-re-review cycle runs entirely **locally**; the server is written to exactly **once**, after you push.

Works whether you review in a **plain repo checkout** (the common case) or a **git worktree**. The skill detects which
and adapts — you never have to know the difference.

**Source of truth: [`references/runbook.md`](references/runbook.md).** Read it in full before driving. It carries the
driving procedure, the four critical gotchas, the submit payload shapes and resolution enums, the heartbeat loop, the
rubric contract, and the accumulated server-gap log. This file is the entry point and the argument resolver; the runbook
is the procedure.

**Rules that apply throughout:**
- `.claude/rules/git-safety.md` — **G11 especially**: this skill NEVER commits or pushes. It hands you an explicit-path
  `git add` line and a commit message; you run them. G10: never `git add .`.
- `.claude/rules/secrets-safety.md` — never print `MANAGER_HUB_TEAM_TOKEN`; reference it by name only.
- `.claude/rules/output-guardian.md` — anything bound for Jira, the PR, or Confluence reads as written by a developer.
- `.claude/rules/agents-safety.md` — the reviewer subagents are read-only and self-contained (A1, A2, A7).

## Prerequisites

| What | Check |
|---|---|
| `code-review-kms` MCP connected | `/mcp` lists it. It provides `mh_list_open_prs`, `mh_start_review`, … |
| `code-lesson` MCP connected | Provides `get_development_rules` — the team-rules gate. Team-scoped; the gate auto-skips if absent, and says so. |
| `MANAGER_HUB_TEAM_TOKEN` in the shell env | Referenced by name only, never printed. |
| PR exists and is pushed | The review reads committed state (`git diff --merge-base origin/<base> HEAD`), not your working tree. |

If an MCP is missing, stop and say which one — do not attempt a partial run.

## STEP 0.5 — Resolve the checkout (do this first)

Run the detection ladder in [`references/checkout-modes.md`](references/checkout-modes.md) to set `CHECKOUT_MODE`:

1. Git reports a worktree (`--git-dir` ≠ `--git-common-dir`) → **`worktree`**.
2. Plain `.git`, current branch == `BRANCH`, HEAD == the PR's `headSha` → **`main`**.
3. Neither → **STOP and ask**, printing what was found (branch, HEAD, dirty files) so the answer is one word.

**Never assume the mode.** It changes STEP 0's preconditions and it *flips* whether the indexed impact reading can be trusted
(runbook server gap #6). Never switch branches or stash on the user's behalf — in `main` mode that is their real
working folder.

## Variables to resolve

| Variable | How to resolve |
|---|---|
| `PR_ID` | A manager-hub CUID (`cm…`) is used directly. A GitHub PR number (`152` / `#152`) → `mh_list_open_prs` (optionally `repoFullName: "FireHawk/<repo>"`), match `prNumber` → `prId`. **Not** the PR number itself. |
| `PR_LABEL` | `owner/repo #number` — display only. |
| `WORKFLOW_ID` | Default `cmpayfzt901zbo79shreoy3zy` unless an argument overrides it. |
| `CHECKOUT` | From the arguments, else the repo folder for the PR's repo. Absolute path when handed to `mh_report_checkout`. |
| `CHECKOUT_MODE` | STEP 0.5 above. |
| `BRANCH` / `BASE_REF` | From the arguments if given, otherwise confirmed against the `headRef`/`baseRef` that `mh_start_review` reports. **The server's reported `baseRef` wins** over any default. |

If a required value cannot be resolved unambiguously, **ask** — do not guess.

## Driving

Follow the runbook's DRIVING PROCEDURE exactly. Two things about it are easy to get wrong and worth stating here:

**The Code Review node's bash block is a prompt carrier, not a command.** Do NOT shell out to `claude -p`. Lift its Team
Context, lens prompts, output contract, and dedup rules; dispatch **one `code-review-depth` subagent per lens, all in a
single message so they run in parallel** (`code-review-breadth` for a cross-repo lens); then merge the packets yourself
into `codeReviewJson`. Count the lenses the block actually carries — N varies between runs; 5 and 6 have both been
observed. The other nodes still run their blocks as returned.

**Run the development-rules gate before classifying findings**, never after (runbook → DEVELOPMENT RULES GATE). Call
`get_development_rules` with `project` from `git remote` (bare `owner/repo` slug), the `language` + `frameworks` actually
imported by the changed files, and `filePath`. A change that **violates** a returned team rule is a valid finding; one
that merely differs from your taste but complies is **not**. In the gate breakdown, self-audit: name the scope you
queried and which rules applied, or record the skip.

## The three gates

Each is a full stop. Present the gate block, wait for an explicit approval, never infer one.

| Gate | Where | You decide | Approving causes |
|---|---|---|---|
| **1 — Pre-submit** | STEP 4.5, once per loop iteration | Which findings are real, in scope, and how each routes (fix now / follow-up / withhold) | Nothing outward. Findings stay local. |
| **2 — Local fix** | STEP 4.6, once per iteration | Which fixes get applied to the checkout this iteration | Local file edits only — no commit, no push |
| **3 — Push** | STEP 4.7, after the loop converges | That the work is ready to leave your machine | **You** push; then the diff is re-uploaded and `mh_submit_result` fires **once** |

**Exit criterion:** zero **`fix now`** high/critical findings. Findings routed to follow-up are deferred by design and do
not block. **Never target the rubric score** — it is computed (`10 − Σ(weights)`), never judged. Chasing the number
instead of the findings is how a round gets gamed.

## Hard rules

- **Never commit or push.** Hand over an explicit-path `git add` + a commit message and stop (G11 / G10).
- **Never stage** local-dev dirt (`.env*`, `environment*.ts`, `server/package.json`) or review artifacts
  (`review-artifacts/**`, `code-review-*`, `*-prompt.txt`, `local-diff.patch`, `manager-hub-open-comments.json`).
  In `main` mode these sit in the user's everyday repo — see checkout-modes.md § Artifact hygiene.
- **Never print** `MANAGER_HUB_TEAM_TOKEN`.
- **Never call `mh_submit_result` on the code_review node before GATE 3.** One submission per round, on pushed state.
- **Never cite an impact reading without checking the mode** — reposphere indexes the committed tree, so in `main`
  mode (dirty working copy) its call-graph answers reflect pre-edit state; local `git diff` is the change-scope authority.
- **Write errors are evidence, not a retry signal.** On an error, stop and surface it verbatim with the `executionId`.

## Next step

After the gate completes, pick EXACTLY ONE action and print the block below with it substituted for `{ACTION_LINE}`.
Substitute the actual ticket key for `{TICKET_KEY}`. Do NOT print the decision table.

**Decision table (reasoning input only):**

| Situation | `{ACTION_LINE}` |
|---|---|
| Findings approved at GATE 1 and you want them applied as a separate pass | `/pr-code-review-fixer {PR_NUMBER}` |
| Review submitted, ticket ready for QA handoff | `/ticket-comment {TICKET_KEY}` |
| Review submitted and the PR is ready to merge | `nothing to do — merge when the second review round also clears` |
| Findings revealed the technical approach was wrong | `/create-spec {TICKET_KEY}` |

**Block to print:**

```
---
**Next step**

{ACTION_LINE}
---
```
