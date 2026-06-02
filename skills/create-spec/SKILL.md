---
name: create-spec
description: "Use after RCA investigation when ready to generate the fix specification and validation plan for a ticket. Triggers on: create spec, generate fix plan, spec for ticket, how to fix GEN-XXXX, full spec package, create all artifacts."
argument-hint: "Jira ticket key (e.g. GEN-1662)"
---

# Create Spec

Generate fix artifacts from an existing RCA. Produces two files under `tickets/{TICKET_KEY}/`:

| File | Template | When |
|------|----------|------|
| `spec.md` | [spec-template.md](./references/spec-template.md) | Always |
| `validation.md` | [validation-template.md](./references/validation-template.md) | Always |

`spec.md` is the single source of truth — it includes RCA summary, technical approach, deployment steps, and rollback. Another developer (or Claude in a new session) can deploy from `spec.md` alone without opening `rca.md`.

Read the relevant template before writing each file. Replace every `[PLACEHOLDER]` with real data. Remove the `## IMPORTANT RULES` block — it is agent instruction, not output content.

**Output guardian:** all output reads as written by a developer. Apply `.claude/rules/output-guardian.md` — never include tool names, session IDs, or any indication of automation.

**Firebase safety:** apply `.claude/rules/firebase-safety.md` — this skill reads live state to build the spec but never writes; every path must state its database (RTDB or Firestore) and use the matching `query_rtdb`/`query_firestore` tool.

**Code search:** apply `.claude/rules/code-search.md` — confirm callers and blast radius with reposphere (`search_with_context`) first; fall back to grep only when reposphere returns empty/low-relevance/errors, stating the reason.

**Agent safety:** apply `.claude/rules/agents-safety.md` — the spec-checker subagent (Step 4) is read-only, returns structured JSON, iteration loop escalates after 3 rounds without convergence.

## NOT This Skill If

- `tickets/{TICKET_KEY}/rca.md` is missing → run `/create-rca` first.
- `rca.md` has a `## Open Questions` section → resolve the questions and re-run `/create-rca` before generating a spec.
- User wants to apply a fix that already has a `spec.md` → use `/apply-fix`.
- User wants the architecture or blast radius of a feature with no ticket attached → use `/impact-analysis`.

---

## Prerequisite

`tickets/{TICKET_KEY}/rca.md` must exist and be current. Check the header for the currency classification:
- `CURRENT` or `PARTIALLY_STALE` → proceed
- `OUTDATED` or no classification → run `create-rca` first to refresh

---

## Step 1: Read and Extract

**Precondition check (do this BEFORE any extraction):** Look for a `## Open Questions` section in `tickets/{TICKET_KEY}/rca.md`. If present, **STOP**. Print the list of open questions to the user with the message: "RCA has unresolved questions — resolve them and re-run /create-rca before generating the spec." Do not draft spec.md or validation.md. Exit.

Read `tickets/{TICKET_KEY}/rca.md` in full. Extract:
- Root cause classification: `CONFIGURATION_GAP` / `CODE_DEFECT` / `DATA_MAPPING_GAP`
- Business context and affected users
- Affected Firebase paths, code files, or templates — **and which database (RTDB or Firestore) each path belongs to**
- Current values of affected paths, expected correct behavior
- Environment context (dev / uat / prod)

## Step 2: Write spec.md

Read [spec-template.md](./references/spec-template.md).

Key rules:
- **Technical Approach is the first-class section.** It must contain four parts:
  1. **What is being changed** — paths, files, or templates being modified (not vague: "fix the config")
  2. **Why this specific change fixes the root cause** stated in rca.md (cross-reference the cause; explain the mechanism)
  3. **Before/after state** — concrete values, not "before bad / after good"
  4. **Risks and caveats** — at least one stated risk, plus what's outside the change set
  The checker fails the spec if any of these four parts is missing or vague.
- **Summary section** — write enough context that someone reading spec.md without rca.md understands what is broken, who is affected, and why
- **Technical Approach** — satisfy the four-part gate above in full.
- **Environment Mapping** — for every Firebase path in the Changes table, classify it:
  - `STABLE` — path is identical across all environments (e.g., `/config/global/featureFlags`)
  - `ENV_SPECIFIC` — path contains an auto-generated key (UUID, push ID) that differs per environment
  - For each `ENV_SPECIFIC` segment: identify the stable field that uniquely identifies the record (e.g., `name`, `label`, `type`), provide a parent-path query + match criteria so someone deploying to UAT can find the correct ID. Include the dev-confirmed value for reference.
  - Mark each write step with `⚠️ ENV_SPECIFIC: resolve ...` if it contains an env-specific path. Remove the note for STABLE paths.
- Use `{ENV}` for all environment references — spec must be reusable for dev and UAT
- Dry-run section must query state **before** each write — use `query_rtdb` or `query_firestore` based on the DB type extracted in Step 1 for each path
- All Firebase paths from rca.md evidence only
- Deployment steps go inline in spec.md (not a separate deploy.md)
- Rollback goes inline in spec.md (not a separate rollback.md)
- For code sections: run `search_with_context({query: "symbolName", repo: "..."})` to confirm callers and capture blast radius in one call — include the callers summary. Then read the actual file and paste exact current code.

## Step 3: Write validation.md

Read [validation-template.md](./references/validation-template.md).

Minimum: 1 happy path + 1 edge case + 1 regression check. Use real entity IDs from the rca.md evidence section — they were already captured during investigation.

## Step 3b: Self-check the Quality Bar

Before dispatching the checker, walk every item in this skill's Quality Bar (and the four-part Technical Approach gate) against your drafts. For each item:

- If it passes, move on
- If it fails AND the fix is mechanical (e.g. "missing ⚠️ ENV_SPECIFIC annotation", "[PLACEHOLDER] left in"), apply it now
- If it fails AND requires fresh data or judgment, leave it for the checker

This pass typically takes 30 seconds and prevents wasted checker iterations on obvious gaps.

---

## Step 4: Verify with spec-checker

After drafting spec.md and validation.md in memory (do not save yet), gate the artifacts through the checker subagent. Run the standard iteration loop defined in `.claude/skills/_shared/contracts/iteration-loop.md` (3 iterations, early-out on stuck gaps, save QUALITY-REPORT on `quality=FAIL`).

1. Read `./checker-prompt.md` from this skill folder.
2. Dispatch a `pipeline-checker` subagent (`.claude/agents/pipeline-checker.md`) with:
   - The full prompt from `checker-prompt.md`
   - The spec.md draft content
   - The validation.md draft content
   - The rca.md path (for cross-validation)
   - Ticket key
3. Parse the JSON result block per `.claude/skills/_shared/contracts/checker-contract.md`: `{ verdict, ticket_key, summary, iteration_hint, gaps[] }`. (`readiness` is RCA-only and is not present in this checker's output.)
4. Apply the iteration loop in `iteration-loop.md`. The loop's `final_classification` resolution for create-spec is:
   - `verdict: PASS` → `final_classification = CLEAR`. Proceed to Step 5.
   - `verdict: FAIL` after 3 iterations OR early-out on stuck gaps → `final_classification = quality=FAIL`. Proceed to Step 5 (Step 5 writes QUALITY-REPORT.md).
   - `verdict: WARN` is treated like PASS for loop-exit purposes. Surface warnings to the user in the Step 5 summary.

The Quality Bar in this file plus the four-part Technical Approach gate are the rubric the checker enforces. Keep `checker-prompt.md` in sync when either changes. Between iterations, print `iteration_hint` from the checker so the user can follow progress.

## Step 5: Save and Summarize

Save the drafts to:
- `tickets/{TICKET_KEY}/spec.md`
- `tickets/{TICKET_KEY}/validation.md`

If `final_classification == quality=FAIL`: also write `tickets/{TICKET_KEY}/QUALITY-REPORT.md` listing every gap from the last checker iteration. Format:

```
# Quality Report — {TICKET_KEY}

**Skill:** create-spec
**Run:** {DATE}
**Final classification:** quality=FAIL

## Open gaps after 3 iterations

- [Quality Bar item] (severity) — issue text
  Suggested fix: text (could not be auto-applied because: reason)
```

After all files saved, tell the user:
- Files created and paths
- Fix type (config / code / mixed)
- Whether dry-run check is needed before applying
- Final classification: CLEAR or quality=FAIL
- (If quality=FAIL) pointer to QUALITY-REPORT.md

Print the Next-step footer matching `final_classification`.

---

## Quality Bar

- [ ] `spec.md` Summary section is readable without opening rca.md — what broke, who is affected, what this fixes
- [ ] `spec.md` Technical Approach explains why this change fixes the root cause
- [ ] `spec.md` Environment Mapping table classifies every path as STABLE or ENV_SPECIFIC
- [ ] Each ENV_SPECIFIC path has a lookup query with a stable match field and dev-confirmed value
- [ ] Write steps with ENV_SPECIFIC paths are annotated with `⚠️ ENV_SPECIFIC: resolve ...`
- [ ] `spec.md` dry-run queries match rca.md evidence paths
- [ ] `spec.md` uses `query_rtdb`/`query_firestore` and `write_rtdb`/`write_firestore` matching the DB type per path — no `[PLACEHOLDER]` data
- [ ] `spec.md` Rollback section has both Option A (session rollback) and Option B (manual fallback)
- [ ] `validation.md` has happy path + edge case + regression; entity IDs from rca.md evidence
- [ ] No invented Firebase paths or placeholder data in any output file

## Next step

After completing this skill, select EXACTLY ONE action from the decision tree below based on `final_classification` from Step 4. Print the block below with the chosen action substituted for `{ACTION_LINE}`. Substitute the actual ticket key for `{TICKET_KEY}`. Do NOT print the decision tree.

**Decision tree (reasoning input only):**

| `final_classification` | `{ACTION_LINE}` |
|---|---|
| `CLEAR` (quality=PASS) | `/apply-fix {TICKET_KEY} dev` |
| `quality=FAIL` (QUALITY-REPORT.md present) | `Review tickets/{TICKET_KEY}/QUALITY-REPORT.md, then re-run /create-spec {TICKET_KEY} or fix manually before /apply-fix` |

**Block to print:**

```
---
**Next step**

{ACTION_LINE}
---
```
