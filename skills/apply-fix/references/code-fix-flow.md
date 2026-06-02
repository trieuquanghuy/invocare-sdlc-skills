# Code Fix Flow (apply-fix Step 5)

Apply code changes specified in `spec.md` with explicit per-file approval and a pre-flight rubric check.

**Called by:** `apply-fix` SKILL.md, after Step 4 (config writes) completes — or directly if the fix is code-only. Skip Step 5 entirely if the spec has no Code Changes section.

**Pre-flight rubric:** `./code-checker-prompt.md` in the apply-fix skill folder. Keep this in sync with Step 5's behavior.

---

## Step 5.0 — Blast-radius summary

For every function/class/method to be changed: run `search_with_context({query: "symbolName", repo: "..."})` to map direct callers and capture the count + whether they span multiple services. Build a blast-radius summary as a list:

```
- symbolName: <N> direct callers, <single-service|multi-service>
```

Note any symbol with > 5 callers OR multi-service callers — these will be flagged by the code pre-flight checker (CR6). The hardcoded threshold (5) is documented in `code-checker-prompt.md`. If your team's threshold differs, edit the rubric directly — no skill should silently use a magic number.

## Step 5a — Code-fix pre-flight check

Before any `Edit` is applied, validate the inputs by dispatching the code-path pre-flight checker subagent.

1. Read `./code-checker-prompt.md` from this skill folder.
2. Dispatch a `pipeline-checker` subagent (`.claude/agents/pipeline-checker.md`) with:
   - The full prompt from `code-checker-prompt.md`
   - Ticket key
   - Repo path (absolute, under `$INVOCARE_ROOT`) and repo name
   - Paths: `tickets/{TICKET_KEY}/spec.md`, `tickets/{TICKET_KEY}/rca.md` (if exists)
   - List of files spec.md plans to modify (extracted from spec.md's Code Changes section)
   - Pre-computed git facts from inside the repo (per `code-checker-prompt.md`'s Inputs section)
   - The blast-radius summary built in Step 5.0
3. Parse the JSON result block per `.claude/skills/_shared/contracts/checker-contract.md`: `{ verdict, ticket_key, repo, branch, summary, iteration_hint, gaps[] }`.
4. Branch on verdict:
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

## Step 5c — Post-edit verification

After all changes:

1. Run `get_review_context({repo: "..."})` to verify only expected files and symbols were modified. Report changed functions and risk scores.
2. Summarize what was modified.

Do NOT create git branches or commits — leave that for the user to handle.
