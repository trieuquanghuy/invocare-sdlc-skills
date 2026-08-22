## IMPORTANT RULES (remove this section before saving):
- This file is written by apply-fix AT RUNTIME — not at deploy-plan creation time.
- For multi-run scenarios, APPEND a new `## Run N` section. Do not overwrite prior runs — this file is a cumulative ledger.
- Replace every `[PLACEHOLDER]`. If a section truly has no content, write `n/a` rather than leaving the placeholder.
- Mode badge in the title must be `REAL` or `DRY-RUN SIMULATION`. Never write `REAL` for a simulation.
- Environment in the title and body is one of `dev` / `uat` / `prod` — substitute the real env at write time.
- No internal tool or command names anywhere, including fenced blocks. Describe operations in developer-facing terms.
- No references to local workspace files in narrative prose — neither bare filenames (`deploy.md`, `session-log.md`, `running-log.md`, `rca.md`, `spec.md`, `rollback.md`), nor paths under `tickets/...`, `sessions/...`, `.claude/...`, nor relative links (`./deploy.md`, `../...`). Use inline prose ("the approved deploy plan", "the session log was updated for this run"). Repo code paths like `FCRM-Web/src/forms/FormController.ts:42` are fine.
- Author identity is the developer who ran the deploy — never hardcode a person's name and never imply AI involvement.
- For dry-run: the running log and per-ticket session log are NOT touched. Say so explicitly under Notes.
- Never include session identifiers. Rollback references remain in the protected audit log.
- For dry-run Verification: every row is `🔵 PENDING — real run only`. Never mark a dry-run row PASS or FAIL — plan inconsistencies belong under Notes, not as a Verification verdict.
- "Code dependency" row only applies for `uat` and `prod` runs. For `dev` runs, drop the row (or mark `n/a — dev is the testbed`).

---

# [TICKET_KEY]: [ENV] Deploy Result — [REAL | DRY-RUN SIMULATION]

**Ticket:** [[TICKET_KEY]]([JIRA_URL]/browse/[TICKET_KEY]) — [JIRA_TITLE]
**Target environment:** `[ENV]`
**Run mode:** **[REAL | DRY-RUN SIMULATION]**
**Run date:** [YYYY-MM-DD] (Sydney)
**Run by:** [developer name]

> [Optional preamble — explain why this run exists. For dry-runs, state explicitly that no Firebase writes were executed and that the audit logs were intentionally not touched. For real runs, state any caveats — partial run, retry of a prior failed run, etc.]

---

## Outcome at a Glance

| Item | Value |
|---|---|
| Status | [✅ PASS / ⚠️ PARTIAL / ❌ FAIL] — [one-line reason] |
| Real Firebase writes executed | [N] |
| Writes succeeded / skipped / aborted | [a / b / c] |
| Real pre-flight reads (safe) | [N] |
| Pre-flight blockers found | [N] ([brief list or "none"]) |
| Outstanding pre-condition for real run | [n/a, OR "Cloud Function X must be live", etc.] |
| Running log updated | [Yes — one line appended | No — dry-run] |
| Session log updated | [Yes — Run N appended | No — dry-run] |

---

## Summary

[2–4 sentences. What was applied (or simulated). Reference the ACs the run satisfies.]

| # | Record | DB | Path | Operation | Outcome |
|---|--------|-----|------|-----------|---------|
| 1 | [name] | RTDB / Firestore | `[path]` | create / partial update / full replacement / delete | ✅ ok / ⚠️ skipped / ❌ failed / 🔵 simulated |

Path stability: [STABLE | ENV_SPECIFIC — `[segment]` resolved from `[match field]` = `[value]`]

---

## Pre-Flight Checks

| Check | Method | Result |
|---|---|---|
| Path exists in `[ENV]` | Real shallow read of `[parent path]` | ✅ / ❌ |
| Current state in `[ENV]` matches the plan's `Before:` snapshot (on fields this write changes) | Real read | ✅ / ⚠️ drift accepted by user / ❌ |
| Source-of-truth value captured (where applicable) | Real read of upstream env for the same path | ✅ / n/a |
| ENV-specific id resolution | [lookup query summary, with resolved id] | ✅ / n/a |
| Code dependency live in `[ENV]` *(uat / prod only — drop for dev)* | Confirmed by user | ✅ / ⚠️ unverified |

---

## Execution Trace

### Step 1 — Start Audited Run  *([REAL | SIMULATED])*

| Item | Value |
|---|---|
| Environment | `[ENV]` |
| Started | `[ISO timestamp]` |
| Audit record | [recorded in the protected deployment log | not created — simulation] |

**Logging actions [performed | skipped — dry-run]:**
- Deployment audit entry recorded with the environment, action, timestamp, and minimized rollback state.

[✓ Session created | (skipped — simulation)]

---

### Step 2.[i] — [Change description]  *([REAL | SIMULATED])*

#### [i].a Pre-write read *(REAL — safe)*

[Path checked] — field-minimized, redacted rollback state:

```[json | twig | text]
[changed fields and minimal rollback dependencies only; redact secret-looking keys]
```

#### [i].b Write *([EXECUTED | NOT EXECUTED])*

| Item | Value |
|---|---|
| Database | RTDB / Firestore |
| Path | `[path]` |
| Operation | create / partial update / full replacement / delete |
| Changed fields | [sanitized field names and values, or size/hash descriptors for large content] |
| Outcome | ✅ succeeded / ⚠️ skipped / ❌ failed / 🔵 simulated |

#### [i].c Sibling-fields integrity check  *([REAL | SIMULATED])*

[For document-level writes] sibling fields on `[parent path]` retained their pre-write values (apart from the standard `updatedAt` / `updatedBy` housekeeping):

| Field | Pre-write value | Post-write value |
|---|---|---|
| [field] | [value] | [unchanged | n/a — was target] |

[✓ Write succeeded | ⚠️ Skipped by deployer | ❌ Failed: [reason] | 🔵 Simulated]

[Repeat the Step 2.[i] block for every write in the deploy plan.]

---

### Step [last] — Complete Audited Run  *([REAL | SIMULATED])*

| Item | Value |
|---|---|
| Status | completed / partial / failed / simulated |
| Writes | [N] |
| Completed | `[ISO timestamp]` |

**Logging actions [performed | skipped]:**
- Final-state lines appended under the same `## Run N` of the session log, with each write's verification command and outcome.

[✓ Session sealed | (skipped — simulation)]

---

## Verification

Each row is a check from the deploy plan's Verification table, run after the writes.

| # | Check | DB | Method | Expected | Result |
|---|---|---|---|---|---|
| V1 | [check name] | RTDB / Firestore | Read current value | [expected outcome] | ✅ PASS / ❌ FAIL / 🔵 PENDING — real run only |
| V2 | [check name] | RTDB / Firestore | [developer-facing method] | [expected] | ✅ / ❌ / 🔵 |

[Real run: populate each row with PASS or FAIL from the actual post-flight read. Dry-run: every row is `🔵 PENDING — real run only` — never PASS or FAIL. If the dry-run plan has an obvious internal inconsistency (the write step and the verification expected value contradict each other), call it out under Notes as `⚠️ Plan inconsistency`.]

---

## Quick Test (manual, performed by deployer after writes)

[Pasted from the deploy plan's Quick Test section — plain app actions, never tool calls. Tick each one as the deployer confirms it.]

- [ ] [Step 1 — app action with expected outcome]
- [ ] [Step 2 — app action with expected outcome]
- [ ] [Step 3 — regression check]

---

## Rollback

**Option A — Audited rollback** *([available on real run | not applicable — simulation])*:

[Use the protected deployment log's rollback reference through the approved rollback procedure. Briefly state what will be restored without exposing the reference.]

**Option B — Manual restore from captured `Before:` snapshot:**

[Restore each affected path to the minimized `Before:` value captured above, using a full replacement or the matching operation through a new audited run.]

---

## Sign-off

- [ ] Code dependency confirmed live in `[ENV]` *(uat / prod only)*
- [ ] Pre-write state captured and reconciled against the deploy plan's `Before:` snapshot (drift accepted explicitly if surfaced)
- [ ] All writes approved per-step (no batched approvals)
- [ ] Verification matrix all PASS [or all PENDING — dry-run]
- [ ] Session log run entry recorded [or n/a — dry-run]
- [ ] Running log line appended [or n/a — dry-run]
- [ ] Real run executed [or this document represents a dry-run only]

---

## Notes

[Free-form. Examples:
- "Dry-run only — `[ENV]` still holds the pre-deploy value. Do not treat this file as proof of deploy."
- "Partial run — write 2 of 3 was aborted because of [reason]. Outstanding work tracked in [follow-up ticket]."
- "Retry of Run 1 — first attempt failed at write 2 with [error]; root cause was [X]; this Run N applied successfully after [fix]."
- "⚠️ Plan inconsistency — write 1 sets `field = X`, but verification V1 expects `field = Y`. Resolve before the real run."
]

For multi-run history, the next apply-fix invocation appends `## Run N+1` below this line — preserving the full ledger.

<!-- append next run below this line -->
