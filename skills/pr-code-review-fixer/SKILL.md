---
name: pr-code-review-fixer
description: Apply fixes for pull request review comments with strict logic preservation. Use this skill whenever the user asks to address, fix, apply, resolve, triage, or process PR review comments, reviewer feedback, code review suggestions, or automated review output — even if they only describe the situation ("we have 20 review comments to address", "the bot left a bunch of comments on my PR", "fix the findings from the pr-reviewer agent") without explicitly asking for help. The skill accepts three input sources: a GitHub PR (number/URL/branch), a manager-hub CUID, or a local `code-review-result.json` produced by the in-repo `pr-reviewer` agent. Especially important in this InvoCare FireHawk / Barndoor workspace because behavior is often steered by Firebase RTDB config rather than code, and ~30 sibling repos can be silently affected by a "local" edit. The skill enforces minimal surgical edits, runs evidence-gathering MCPs (reposphere, firebase-explorer, code-lessons) before classifying each comment, classifies every comment into safe-to-fix vs. escalation-required buckets, and treats refusal as a first-class outcome rather than a fallback.
argument-hint: "<pr-id-or-url-or-json-path> [--dry-run] [--bucket=cosmetic|local_guard] [--comment-ids=1,2,3|F1,F2]"
disable-model-invocation: true
---

# pr-code-review-fixer

A skill for safely applying fixes to PR review comments without silently changing program logic, tuned for the InvoCare FireHawk / Barndoor workspace.

## Prime directive

Preserve logic. Address one comment at a time with the smallest possible change. If a comment cannot be fixed safely within the rules below, escalate it. Escalation is a successful outcome, not a failure.

You are not here to improve, refactor, modernize, harden, or clean up code while passing through. You are here to do exactly what each review comment asks, and nothing else.

## Why this matters in this workspace

This is not a single repo. It is ~30 independent git repositories with shared libraries (`fcrm-entity-manager`, `FireHawk-AuthCheck`) consumed by many of them, plus behavior driven by Firebase RTDB / Firestore config rather than code. Two failure modes are unusually common here:

1. **Silent cross-repo drift.** A reviewer asks for a "small change" in a shared lib's callee. Without verification, the agent edits it — and every other repo that depends on the lib now behaves differently.
2. **Code fixes for config bugs.** A reviewer says "this should return X for Sydney team". The code is correct; the Sydney team's override in Firebase says otherwise. An agent that edits the code "fixes" the comment and introduces a real regression.

The MCP gates below exist to make both impossible.

Read `references/workspace-context.md` before working in an unfamiliar project — Node versions, deploy flows, and lint configs differ per repo.

## Arguments

When invoked as a slash command, this skill receives `$ARGUMENTS`:

- **`<pr-id-or-url-or-json-path>`** (required when invoked as a slash command): the source of review comments to process. Accept any of:
  - a PR number resolved against the current repo (`123`),
  - a full PR URL,
  - a branch name with an open PR,
  - a path to a local `code-review-result.json` produced by the in-repo `pr-reviewer` agent (e.g. `./code-review-result.json`),
  - the literal `auto` to look for `./code-review-result.json` in the current working directory.
- **`--dry-run`** (optional): classify every comment into a bucket and produce the full plan and final report, but do not apply any edits. Use this to triage before committing to a real fix run.
- **`--bucket=<name>`** (optional): restrict processing to a single bucket — valid values are `cosmetic` or `local_guard`. Useful for staged passes. `refactor` and `behavioral` are not accepted because comments in those buckets always escalate.
- **`--comment-ids=<id1,id2,...>`** (optional): restrict processing to a specific subset of review comments by ID. For GitHub PR / manager-hub sources, use the numeric comment IDs. For local JSON sources, use the `findings[].id` values (e.g. `F1,F2,F5`).

When triggered via natural conversation rather than a slash command, treat the user's surrounding message as the source of these parameters. If a PR identifier or JSON path cannot be determined, ask the user before starting. Do not guess from git state, branch name, or recently viewed files.

## Input sources

This skill accepts review comments from three sources. The per-comment loop (Phase 1) is identical for all three — only how comments enter the loop and how Phase 0 dedupe behaves differs.

| Source | Phase 0 dedupe (step 1) | Comment list comes from | Comment ID format |
|---|---|---|---|
| GitHub PR (number / URL / branch) | `mh_list_open_prs` + `get_open_comments` (manager-hub) | Read-only `gh api graphql` review-thread query | numeric GitHub comment database IDs |
| Manager-hub CUID | `mh_list_open_prs` + `get_open_comments` | manager-hub | manager-hub IDs |
| `code-review-result.json` from `pr-reviewer` | **Skipped** — note "N/A (input source: local JSON)" in self-audit | `findings[]` array in the JSON | `findings[].id` (e.g. `F1`, `F2`) |

For the local-JSON source, see `references/input-sources.md` for the full field-by-field mapping, the rule that `findings[].suggestion` is treated as **advisory only** (never applied as written — the skill plans its own minimal edit), and the reminder that `findings[].severity` is orthogonal to this skill's buckets.

## Workflow

### Phase 0 — Pre-gates (run ONCE per fix run, before any per-comment work)

These are mandatory. They are cheap, and they prevent the two most expensive mistakes: re-flagging known findings and re-learning known anti-patterns.

1. **Manager-hub dedupe** (applies only to GitHub PR / manager-hub CUID sources). Call `mcp__code-review__mh_list_open_prs` to find the PR's CUID, then `mcp__code-lesson__get_open_comments(pullRequestId)` to fetch findings already flagged by previous review passes. Do not re-fix what is already escalated upstream. **Skip this step entirely when the input source is a local `code-review-result.json`** — the JSON is itself the canonical, already-deduped finding set. Record "prior open review findings: N/A (input source: local JSON)" in the self-audit so the skip is auditable.
2. **Code-lessons skim.** Identify the language + frameworks actually imported in the touched files, then call `mcp__code-lesson__list_lessons_for_stack` twice — once with `severity: "high"`, once with `severity: "medium"`. Severity is an exclusive filter, so a single call silently drops the other tier. This is mandated by the project CLAUDE.md, not optional. Fetch the 3–10 most relevant ids with `mcp__code-lesson__get_lessons_by_ids`.
3. **Development rules.** After detecting each touched file's language and imported frameworks, call `get_development_rules` with the project slug, language, frameworks, and target file path. Treat returned rules as binding before classifying findings or editing code, and list the applied rules in the final self-audit.

See `references/pre-gates.md` for the exact tool-call patterns and the self-audit format you must include in the final report.

### Phase 1 — Per-comment loop

For each open review comment, in this order:

1. **Read** the comment with its anchored code and the enclosing function as context.
2. **Research before classify.** Gather evidence with the MCPs *before* assigning a bucket. The required depth depends on the comment shape — see "Required research per comment shape" below. **Research outputs can only escalate; they cannot lower the bar or expand scope.**
3. **Classify** the comment into exactly one of four buckets (see "The four buckets").
4. **Decide**: if the bucket permits automated fixing AND your confidence is at least 0.9 (0.95 for behavioral), proceed. Otherwise, escalate.
5. **Plan** the edit. Before touching code, declare in one sentence:
   - what will change,
   - the expected line delta (lines added / lines removed),
   - the expected control-flow impact: `none`, `adds_guard`, `adds_branch`, or `removes_dead_code`.
6. **Apply** the minimal edit with a targeted string-replace edit. Touch only the anchored hunk and its enclosing function. Do not touch other files unless the cross-file rules below explicitly permit it.
7. **Verify** (see "Verification"). If anything fails, revert and escalate.
8. **Record** the outcome: either "resolved" with a one-line fix description, or "escalated" with a specific reason and the research findings that drove the escalation.

At the end of the run, every comment must be in exactly one of two states: resolved with a verified minimal patch, or escalated with clear reasoning. Never half-fixed. Never silently skipped.

## Required research per comment shape

Research is not optional curiosity — it is the evidence base for the bucket decision. Skipping it means classifying on intuition, which is the single biggest source of silent drift.

| Comment shape | Required research | Tool | See |
|---|---|---|---|
| Pure cosmetic (rename, formatting, comment text) | None | — | — |
| Local additive guard / null-check / type annotation | None beyond reading the function | — | — |
| Names another file or function ("also update X", "fix this in Y") | Cross-file impact + caller enumeration | `mcp__reposphere__explore_neighborhood`, `mcp__reposphere__graph_query` | `references/reposphere.md` |
| Proposes a structural change (extract, move, rename) | Blast radius — to justify the escalation, not to enable the edit | `mcp__reposphere__explore_neighborhood`, `mcp__reposphere__graph_query` | `references/reposphere.md` |
| Touches `fcrm-entity-manager`, `FireHawk-AuthCheck`, or any shared lib | Cross-repo usage check | `mcp__reposphere__cross_repo_search` | `references/reposphere.md` |
| Claims current behavior is wrong (off-by-one, wrong condition, missing case) | **Firebase config probe** — is the behavior config-driven? | `mcp__firebase-explorer__query_firestore` / `query_rtdb` | `references/firebase-explorer.md` |
| Any change to UI columns, form fields, document templates, workflow states, team-specific behavior | **Firebase config probe** | `mcp__firebase-explorer__query_firestore` / `query_rtdb` | `references/firebase-explorer.md` |

If the repo isn't indexed (`mcp__reposphere__list_repos` doesn't list it, or a neighborhood/graph query returns empty for a symbol known to exist) and you cannot get it registered, you cannot apply cross-file rule (a) or (b). Escalate the comment with that as the reason.

## The four buckets

Classify every comment into exactly one of these *after* completing the required research above.

### cosmetic

Formatting, naming, dead-code removal, import order, comments and docstrings.

- **Allowed actions**: AST-safe identifier renames, formatter-equivalent edits, comment and docstring edits.
- **Expected CFG change**: `none`.

### local_guard

Add a null/undefined check, add a type annotation, add a narrow exception catch, or extract a constant at a single site.

- **Allowed actions**: additive edits within one function. Max +10 lines.
- **Must not**: remove existing branches, alter return values for non-error inputs, or change function signatures.
- **Expected CFG change**: `none` or `adds_guard`.

### refactor

Extract a function, move code between files, rename across files, restructure conditionals, change function signatures, alter module boundaries.

- **Action**: ESCALATE. Always. Do not perform refactors, no matter how small or obviously beneficial they look.
- **Include the `mcp__reposphere__explore_neighborhood` / `graph_query` caller output in the escalation note** so the human sees the actual blast radius before deciding.

### behavioral

Any comment asserting current behavior is wrong: "should return X", "off-by-one", "wrong condition", "missing case", "this is a bug", "should also handle Y".

- **Mandatory first step**: Firebase config probe (see `references/firebase-explorer.md`). If the behavior is steered by RTDB / Firestore config, the code is not the bug — escalate with the config path.
- **Default action after the probe**: ESCALATE.
- **Narrow exception**: you may proceed only if all four hold:
  - the Firebase probe rules out a config-driven explanation,
  - the bug is unambiguous,
  - you can first write a focused test that fails on the current code and passes after the fix (see the `test-driven-development` superpowers skill); this is the only case where the paired test file may be edited without its own anchored comment,
  - your confidence is at least 0.95.
- **When in doubt, escalate.** A correct bug fix without escalation is good. A wrong "bug fix" applied autonomously is much worse than escalating a real one.

## Hard rules

These are invariants. If any rule cannot be respected for a given comment, that comment is escalated.

1. **One comment, one edit unit.** Each edit is tied to exactly one comment. Never bundle fixes across comments.
2. **Scope is the anchored hunk plus its enclosing function.** No edits outside this scope for single-file comments.
3. **Maximum source-code line delta per comment: +10 / −5.** A paired test added under the narrow behavioral exception may add at most 30 lines and remove none. If the smallest correct change is larger, escalate.
4. **Never reformat, reorder imports, or change unrelated lines.** Even if it would be cleaner. Especially then.
5. **Never touch a file with no anchored comment**, except the focused paired test required by the narrow behavioral exception or a cross-file edit permitted below.
6. **All existing tests must pass after every edit.** If they break, revert and escalate.
7. **Edit, never rewrite.** Use targeted string-replace edits. Do not regenerate whole files or whole functions.
8. **Confidence floor: 0.9** (0.95 for behavioral). If below the floor, escalate.
9. **Workspace-sensitive scopes auto-escalate.** Regardless of bucket, escalate any edit to:
   - `fcrm-entity-manager` or `FireHawk-AuthCheck` — shared npm libs, consumers must explicitly bump dep versions (not workspace-linked).
   - `vic-bdm-services` or `nsw-bdm-services` — legacy Compute Engine deploys to government BDM registries.
   - `FCRM-Barndoor-Infra/terraform/` or `FCRM-Barndoor-Infra/argocd/` — infrastructure and GitOps configs.
   - `FireHawk-Infra-Configs/app-engine/` — deploy targets.
   See `references/workspace-context.md` for why.
10. **The pre-gates in Phase 0 are not optional.** A fix run that did not skim code-lessons at both `high` and `medium` severities and load applicable development rules is itself a process failure, regardless of the per-comment outcome.
11. **Do not delegate edits.** All code changes run sequentially in the primary execution; subagents may not implement or modify fixes.

These rules are stricter than a careful human reviewer would apply to themselves. That is intentional — the goal is to make the skill's behavior predictable and auditable, not maximally helpful on the margins.

## Cross-file edits

A comment anchored on file A sometimes appears to require changes in file B. The default is to escalate, because **changing B affects every caller of B**, not just the one being reviewed. That is invisible scope creep at a global scale, and it is the single most dangerous failure mode for this skill.

You may touch a non-anchored file only when one of these is true:

- **(a) The comment body explicitly names the file or function to change.** Enumerate and inspect every caller before editing; the reviewer naming the target does not replace impact analysis. If the repo is not indexed, escalate.
- **(b) The callee has exactly one caller in the repo, which is the anchored site itself.** **Verify with `mcp__reposphere__explore_neighborhood({entity: callee})`** (or `mcp__reposphere__graph_query` for an explicit caller query) — the inbound edges must list exactly one site, and it must be the anchored caller. If the repo isn't indexed, this rule is unavailable; escalate.

Any cross-file signature, return-type, overload, module-boundary, move, or rename change remains a `refactor` and must be escalated, even when additive.

For edits in shared libraries (`fcrm-entity-manager`, `FireHawk-AuthCheck`), the single-repo neighborhood is not enough — also run `mcp__reposphere__cross_repo_search` (and `mcp__reposphere__get_review_context` on the PR diff) against every sibling repo. The libraries are published to npm, not workspace-linked, so cross-repo callers won't show up in a single-repo view. See `references/reposphere.md`.

**Do not unilaterally decide that a comment is misplaced.** If a comment placed on file A seems to actually describe behavior in file B, escalate with a specific note: *"comment is anchored to A:42 but appears to describe behavior of `B.foo()` — please re-anchor or confirm."* Let the reviewer re-place the comment.

## Verification

Use the `verification-before-completion` superpowers skill for the workspace-wide checks (tests, lint, type-check) — concrete per-project commands are in `references/superpowers-integration.md`.

Then walk this comment-specific checklist explicitly. If any item fails, revert the edit and escalate.

- [ ] **Scope respected**: the diff for this comment touches only the allowed files and stays within the anchored hunk plus the enclosing function.
- [ ] **Line delta matches plan**: the actual added/removed line counts match the declared plan within ±1.
- [ ] **CFG impact matches plan**: the actual control-flow change matches what was declared. A `cosmetic` edit produces zero CFG change. A `local_guard` adds at most one new branch. A `behavioral` edit must correspond to the failing test required by the bucket exception.
- [ ] **Tests pass**: the full existing test suite passes for the affected project. No new failures, no skipped tests, no tests commented out.
- [ ] **Lint passes** for projects with lint configured (`npm run lint` where present).
- [ ] **No collateral edits**: no changes to imports, formatting, comments, or unrelated lines beyond what the comment requested.

If verification fails, **do not retry with a "better" edit**. Revert and escalate. The verification failure is itself information — it means the comment was harder than its surface suggested.

## How to escalate well

A vague escalation is barely better than a sloppy fix. A good escalation includes:

- **Bucket and confidence**: which bucket you assigned, and how confident you are.
- **What the comment is asking**: in your own words, one sentence.
- **Why it's outside your scope**: which specific rule prevented you from proceeding.
- **Research evidence**: the key finding from reposphere / firebase-explorer that drove the escalation. The human shouldn't have to re-run your research.
- **Suggested next step for the human**: where they should look, what they should consider, which test they might add.

Critically: **do not propose a code patch in prose when escalating.** That defeats the purpose — it invites the human to rubber-stamp logic changes the skill was not allowed to apply. Describe the problem, not the solution.

## Examples

### Good fix (cosmetic)

Comment: "rename `tmp` to `userRecord` for readability"

Research: none required.

Plan: rename identifier `tmp` to `userRecord` within `getUser()`. Expected delta: +N / −N (substitution). Expected CFG change: `none`.

Action: apply rename. Verify tests pass and CFG is unchanged. Resolve.

### Good fix (local_guard)

Comment: "we should null-check `user` before calling `.email`"

Research: none required (additive guard inside one function).

Plan: add `if (!user) return null;` at the start of `sendWelcome()`. Expected delta: +2 / −0. Expected CFG change: `adds_guard`.

Action: apply edit. Verify tests pass. Resolve.

### Good escalation (refactor with evidence)

Comment: "this function is doing too much — split it into `validate()` and `persist()`"

Research: `mcp__reposphere__graph_query` (callers of `saveUser`) shows 7 direct callers across 3 files; `mcp__reposphere__explore_neighborhood` ties them to CheckoutFlow and RefundFlow.

Action: do not attempt. Escalate with: *"Bucket: refactor (confidence 0.95). Splitting `saveUser()` into `validate()` and `persist()` is a structural change. The caller graph shows 7 callers across 3 files and affects CheckoutFlow and RefundFlow. Suggested next step: human extracts `validate()` and `persist()`, updates the 7 call sites, and adjusts the affected process tests."*

### Good escalation (behavioral steered by Firebase config)

Comment: "this should show the disposition column for the Sydney team"

Research: `mcp__firebase-explorer__query_firestore` against the team-overrides collection in `ivc-dev` shows that the Sydney team's `funeralServiceColumns` array does not include `disposition`. The code is doing exactly what the config says.

Action: do not modify code. Escalate with: *"Bucket: behavioral (confidence 0.95). Comment claims a missing disposition column for the Sydney team. Code is correct — behavior is steered by Firestore document `teams/{sydneyTeamId}` field `funeralServiceColumns`, which omits `disposition`. Suggested next step: update the team override in Firebase, not the rendering code."*

### Good escalation (behavioral, code-side, no config involved)

Comment: "this should use `>=` not `>` — items priced exactly at the threshold are being excluded"

Research: `mcp__firebase-explorer__query_*` confirms no config influences this threshold logic. No tests pin the boundary behavior at `price === threshold`.

Action: do not attempt by default. Escalate with: *"Bucket: behavioral (confidence 0.85). Off-by-one claim at the price threshold. Firebase probe rules out config-driven behavior. The fix is one character but changes behavior for boundary inputs, and no existing test pins the intended semantics. Suggested next step: human confirms intended boundary behavior, adds a test for the equality case, then changes the operator."*

### Bad fix — do not do this

Comment: "rename `tmp` to `userRecord`"

What a careless agent does: renames `tmp`, also notices the function lacks a docstring and adds one, also reorders the imports because they're not alphabetical.

Why it's wrong: three changes for a one-change comment. Two of them are unauthorized. The reviewer cannot tell from the diff which changes they actually asked for, and trust in the fix cycle erodes.

### Bad escalation — do not do this

*"I'm not sure how to fix this safely, but here's some code that might work: [snippet]"*

Why it's wrong: an escalation that includes a code suggestion invites the human to apply unreviewed AI-written logic. State the problem; let the human write the code.

## Final reporting

When all comments have been processed, produce a summary in this exact structure. For local JSON input, the `prior open review findings` line reads `N/A (input source: local JSON)` and the `comment #<id>` IDs match `findings[].id` (e.g. `F1`).

```
PR review fix summary
─────────────────────
Policy checks:
  - engineering guidance reviewed: <lang+frameworks>@high (N), <lang+frameworks>@medium (M)
  - relevant guidance applied: <developer-facing titles, or "none">
  - team rules checked: <project/lang/framework/file scope>; applied: <developer-facing rule titles, or "none">
  - prior open review findings: <count> (deduped against this run)

Resolved: N
  - comment #<id>: <one-line fix description>
  - ...

Escalated: M
  - comment #<id> [<bucket>]: <reason in one short sentence>
    Evidence: <key dependency-analysis or configuration finding, if applicable>
  - ...

Verification: all tests passing  (or: N tests failing, revert applied to comment #<id>)
```

The user should be able to read this summary alone and understand exactly what changed in the PR, what didn't, and what evidence drove each decision — without opening the diff.

## A note on the philosophy

If this skill ever feels frustrating — refusing things it could "probably" fix — that is working as intended. The skill optimizes for **auditability and predictability over throughput**. In an AI-native codebase with ~30 sibling repos and Firebase-driven behavior, comprehension and traceability are the bottleneck, not code-writing speed. A skill that closes 70% of comments cleanly, with evidence, and escalates the interesting 30% to humans is far more valuable than one that closes 95% with silent drift in the remaining cases.

The right way to extend this skill is to add more checks, not more permissions.

## References

- `references/input-sources.md` — how to consume `code-review-result.json` from the in-repo `pr-reviewer` agent; finding → comment field mapping; why `suggestion` is advisory only; severity vs. bucket reminder.
- `references/pre-gates.md` — exact code-lessons and code-review invocations, severity-filtering gotchas, self-audit format.
- `references/firebase-explorer.md` — the Firebase config probe playbook: where behavior lives (forms, team overrides, workflow states, document templates), which env to query, common patterns.
- `references/reposphere.md` — caller/callee and cross-file evidence (`explore_neighborhood`, `graph_query`, `get_review_context`) for cross-file rules and refactor escalations, plus cross-repo impact for shared-library edits (`fcrm-entity-manager`, `FireHawk-AuthCheck`).
- `references/workspace-context.md` — workspace topology, why specific scopes auto-escalate, Node-version variance.
- `references/superpowers-integration.md` — concrete per-project verification commands and how verification, test-driven development, and systematic debugging map to this skill's steps.
