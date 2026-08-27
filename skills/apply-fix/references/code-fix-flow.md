# Code Fix Flow (apply-fix Step 5)

Apply code changes specified in `spec.md` with explicit per-file approval and a pre-flight rubric check.

**Called by:** `apply-fix` SKILL.md, after Step 4 (config writes) completes — or directly if the fix is code-only. Skip Step 5 entirely if the spec has no Code Changes section.

**Pre-flight rubric:** `./code-checker-prompt.md` in the apply-fix skill folder. Keep this in sync with Step 5's behavior.

**Local dev overrides:** apply `.claude/rules/local-dev-overrides.md` throughout — pre-existing run-local config modifications (FCRM-Web's `environment*.ts`, `package.json`/lock, `.nvmrc`, `.gitignore`, etc.) are expected noise: never stage them into the fix commit, never revert/stash them, never count them as part of the diff.

---

## Step 5.-1 — Quality gates (MANDATORY before any edit)

The code this flow writes has shipped with quality problems; these gates are the fix. Run BOTH, in one parallel turn, before Step 5.0:

1. **Team standards:** `get_development_rules({project, language, frameworks, filePath})` for the repo and each file type you will touch. Returned rules are **binding constraints** — a rule that conflicts with the spec's approach stops the run for a user decision, never a silent override.
2. **Lessons corpus:** `list_lessons_for_stack` at severity `high` AND `medium` (two calls, same turn — the filter is exclusive), then `get_lessons_by_ids` for the 3–10 relevant to the diff shape. Applied lessons are constraints too.

Carry the applicable rules/lessons into Step 5b as a written checklist; the Step 7 summary must name which applied and how each was followed.

## Step 5.0 — Blast-radius summary

For every function/class/method to be changed: run `search_with_context({query: "symbolName", repo: "..."})` to map direct callers and capture the count + whether they span multiple services. Build a blast-radius summary as a list:

```
- symbolName: <N> direct callers, <single-service|multi-service>
```

Note any symbol with > 5 callers OR multi-service callers — these will be flagged by the code pre-flight checker (CR6). The hardcoded threshold (5) is documented in `code-checker-prompt.md`. If your team's threshold differs, edit the rubric directly — no skill should silently use a magic number.

## Step 5a — Code-fix pre-flight check

Before any `Edit` is applied, validate the inputs by dispatching the code-path pre-flight checker subagent.

1. Dispatch a `pipeline-checker` subagent (`.claude/agents/pipeline-checker.md`) with a self-contained prompt that inlines:
   - The full rubric from `.claude/skills/apply-fix/code-checker-prompt.md`; a file-path reference alone is not sufficient.
   - The full task description and every input needed to evaluate it.
   - Ticket key
   - Repo path (absolute, under `$INVOCARE_ROOT`) and repo name
   - Paths: `tickets/{TICKET_KEY}/spec.md`, `tickets/{TICKET_KEY}/rca.md` (if exists)
   - List of files spec.md plans to modify (extracted from spec.md's Code Changes section)
   - Pre-computed git facts from inside the repo (per `code-checker-prompt.md`'s Inputs section)
   - The blast-radius summary built in Step 5.0
2. Parse the JSON result block per `.claude/skills/_shared/contracts/checker-contract.md`: `{ verdict, ticket_key, repo, branch, summary, iteration_hint, gaps[] }`.
3. Branch on verdict:
   - **FAIL** → print every blocker gap, exit. No `Edit` calls happen.
   - **WARN** → print every warning gap, ask `Proceed anyway? (yes/no)`. If `no` → exit. If `yes` → record acknowledged warning rule IDs (e.g. `CR5, CR6`) for the Step 7 summary, continue.
   - **PASS** → continue silently.

If the checker dispatch fails or returns malformed JSON: print `Code pre-flight could not run: <reason>. Without pre-flight, no automated check that the working tree, branch state, and spec scope are sane.` Then ask `Proceed without pre-flight? (yes/no)`. Capture `Code pre-flight: SKIPPED (dispatch failure: <reason>)` for the Step 7 summary.

This pre-flight runs ONCE per Step 5 invocation — it does not iterate.

## Step 5b — Per-file edit loop

Once Step 5a passes (or warnings are acknowledged):

1. Read the current file to confirm it matches what spec.md describes.
2. Show the before/after diff clearly.
3. Ask: "Apply this change? (yes / no)"
4. On yes: use the Edit tool to make the change.

## Step 5b.1 — Unit tests cover every code change (MANDATORY)

Every code change in this run must be covered by unit tests before verification:

1. **Map the coverage:** for each changed function/method/branch, name the test that exercises it. Follow the repo's existing test framework, file layout, and naming (`*.spec.ts` / `*.test.js` next to source or under the repo's test dir — match what's already there, per CQ8).
2. **Bug fix → regression test first-class:** at least one test must encode the ticket's symptom — it FAILS on the pre-fix code and passes on the fixed code (per `engineering-conduct.md` EC9, the test protects the *why*, not just the mechanics). State which test that is.
3. **New/changed logic → cover the real branches:** happy path plus the empty/null/error paths the change introduces (CQ1). Don't gold-plate — no tests for inputs upstream code already prevents (anti-overengineering AO2); cover what the diff actually changed.
4. **Update stale tests honestly:** if existing tests fail because the behavior intentionally changed, update them to encode the new intent — never delete or skip a test to make the suite green without saying so.
5. **No test infrastructure available** (framework absent, or environment can't run it — e.g. iOS in-session): write the tests anyway if the framework exists but can't run here, and state `tests written but not executed: <reason>`; if no framework exists at all, say so explicitly and record it in Step 5d — silence is not an option.

The coverage map (changed symbol → test) goes into the Step 7 summary and the Step 5d log entry.

## Step 5c — Post-edit verification (objective checks, not vibes)

After all changes, in this order:

1. **Scope check:** `git diff --name-only` and `git diff --stat` — confirm only the files listed in spec.md's Code Changes section were modified (local dev overrides per `.claude/rules/local-dev-overrides.md` don't count). Surface any unexpected file.
2. **Toolchain check — run whatever the repo provides.** Detect from `package.json` scripts (or the repo's README/CI config) and run the applicable subset: `lint`, `typecheck`/`tsc --noEmit`, and the test command scoped to the touched files — which MUST include the Step 5b.1 tests (new and updated); report their pass/fail individually. Report actual output. A failure is a blocker: fix it or surface it — never summarize the run as done with a red toolchain. If the repo genuinely has no runnable checks in this environment (e.g. iOS build needs Xcode signing), say so explicitly: `toolchain checks unavailable: <reason>` — silence is not an option.
3. **CQ self-review:** re-read the full diff against `code-quality.md` CQ1–CQ13 and the Step 5.-1 checklist; name the checks applied in the summary.
4. **Independent review pass (non-trivial diffs):** if the diff touches logic (not a pure rename/typo), dispatch ONE `code-review-depth` agent with the changed file(s) + diff. Fix or explicitly acknowledge every blocker/warning finding before declaring done. Skip only for trivial diffs, and say so.
5. Summarize what was modified.

Do NOT create git branches or commits — leave that for the user to handle.

## Step 5d — Run logging (code fixes get a ledger entry too)

Append a `## Run N` entry to `tickets/{TICKET_KEY}/session-log.md` (create the file if needed):

```
## Run N
- **Session ID:** n/a (code-only)
- **Environment:** n/a (code — repo {REPO}, branch {BRANCH})
- **Date:** {DATE TIME}
- **Action:** code-apply
- **Files edited:** {list}
- **Tests:** {coverage map: changed symbol → test file, incl. the regression test; or "tests written but not executed: <reason>" / "no test framework in repo"}
- **Verification:** {lint/typecheck/test results + review-pass outcome}
```

Without this, code-only fixes are invisible to `/task-status`, re-apply rounds, and the audit trail. Mixed fixes append this as part of the same run entry as the config writes.
