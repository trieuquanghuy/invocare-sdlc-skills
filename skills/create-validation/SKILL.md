---
name: create-validation
description: "Generate the QA validation plan (tickets/{KEY}/validation.md) with test scenarios covering every acceptance criterion or bug symptom. Use whenever the user asks to create/update a validation plan, write test cases for a ticket, build QA scenarios, check test coverage of ACs, or says 'validation for GEN-XXXX' — works standalone from an existing rca.md/spec.md, and is also invoked by create-spec as its Step 3."
argument-hint: "Jira ticket key (e.g. GEN-2759)"
disable-model-invocation: true
---

# Create Validation Plan

Produce `tickets/{TICKET_KEY}/validation.md` — the UI-level test scenarios QA (or a dev who didn't write the fix) follows to prove the work, with a **Coverage table** proving every AC or bug symptom is tested.

**Focus:** the validation plan answers one question — *does every acceptance criterion (story) or reported symptom + regression surface (bug) have a scenario that proves it?* Fix analysis belongs in rca.md; the change plan belongs in spec.md. This file carries scenarios and their coverage mapping, nothing else.

**Output guardian:** apply `.claude/rules/output-guardian.md` — no tool names, session IDs, or automation references in the artifact.
**Firebase safety:** apply `.claude/rules/firebase-safety.md` — read-only. Only `query_rtdb`/`query_firestore`/ES reads to verify test-data records exist; never any write.

## When to Use

- Standalone: "write test cases for GEN-XXXX", "create the validation plan", "does our testing cover all ACs?"
- Called from `create-spec` Step 3 (the spec run passes its in-memory spec.md draft as context)
- Re-run after a fix changes scope: rewrite validation.md in place (update-in-place semantics — no "v2" scenario blocks; the file reads as the current plan)

## Inputs (in priority order)

1. `tickets/{TICKET_KEY}/rca.md` — **the coverage source of truth**: Section 2 (Acceptance Criteria / Steps to Reproduce) defines what must be covered; Section 7.5 Gap Analysis (stories) and the Evidence table supply test data and paths.
2. `tickets/{TICKET_KEY}/spec.md` — Before/after state (pre-condition expected values), Changes table (regression surface), Acceptance Criteria checkboxes.
3. The Jira ticket — only when rca.md is missing; fetch ACs from the ticket and note in the header that no RCA exists.

If neither rca.md nor a fetchable ticket exists, stop and say what's missing — never invent ACs.

## Workflow

### Step 1: Extract the coverage list

From rca.md Section 2 (or Jira ACs as fallback), list every item to be proven:

- **Story** → every AC, numbered as in the source (AC1, AC2, …).
- **Bug** → the reported symptom (as "the fix works") + each regression surface from spec.md's Changes table / rca.md Impact Assessment (as "nothing adjacent broke").

This list IS the contract. Everything else in the skill exists to map scenarios onto it.

### Step 2: Design scenarios — fewest that cover everything

Design the minimum scenario set where every coverage item maps to at least one scenario (per `anti-overengineering.md` AO2/AO3):

- One end-to-end flow often proves several ACs — map them all to that one scenario rather than writing near-duplicate scenarios per AC.
- Always include: 1 happy path, 1 edge case, 1 regression check (template minimum). More only when the coverage list demands it.
- Steps are UI-level and executable by someone who didn't write the fix: exact URL/screen, exact element, exact value, expected result per step.
- Use real entity IDs from rca.md evidence. Verify each test-data record still exists with a read query before citing it.
- An item that genuinely cannot be tested yet (missing data, blocked dependency) gets a **NOT COVERED** row with the reason — visible in the table, never silently dropped and never faked with an untestable scenario.

### Step 3: Write validation.md

Read [validation-template.md](./references/validation-template.md) and follow it: Pre-Condition (cross-references spec.md's Dry Run — don't re-copy queries), Login & Access, Test Data, **Coverage table**, scenarios, Post-Fix DB confirmation, Sign-Off. Remove the IMPORTANT RULES block before saving.

### Step 4: Self-check coverage before declaring done

Walk the Coverage table:
- Every item from Step 1 has a row. Every row maps to a scenario number that exists, or is NOT COVERED with a reason.
- No scenario exists that maps to zero rows — an unmapped scenario is scope creep; cut it.
- In the done-summary, state the count: "N of M ACs covered by K scenarios; X NOT COVERED (reasons listed)".

When invoked from create-spec, the spec's checker validates this file (rule S9/S10); standalone runs rely on this self-check.

## Coverage Rules (the point of this skill)

1. **Complete:** every AC / symptom appears in the Coverage table. A missing row is the one unacceptable outcome.
2. **Honest:** NOT COVERED with a reason beats a fake scenario. Coverage gaps are surfaced, not hidden.
3. **Minimal:** the fewest scenarios that achieve rows-all-mapped. Don't write a scenario no coverage row needs, don't split one flow into three scenarios for symmetry, don't test behavior the ticket doesn't name. The Coverage table is also the over-engineering guard: scenarios without a row are cut.
4. **Executable:** each step names screen, element, value, expected result. A scenario QA can't run without asking questions isn't done.

## Next step

- Invoked from create-spec: return control — the spec flow continues (checker, save).
- Standalone: `Validation plan saved to tickets/{TICKET_KEY}/validation.md — {N}/{M} items covered by {K} scenarios.` Suggest `/apply-fix {TICKET_KEY}` if the fix isn't applied yet, else hand to QA.
