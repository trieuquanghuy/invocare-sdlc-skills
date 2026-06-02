## 1. Before the Fix

**Correct requirement:**
{What the correct behavior/config should be — reference the specific requirement if available}

**Current state (broken):**
{What the config/code actually looked like and WHY it was broken — plain language}
{Numbered list of each issue found}
{1 paragraph with specific impact — record counts, percentages, concrete data}

{If RCA exists on Confluence, add:}
RCA: [{RCA page title}]({confluence_url})

## 2. Fix ({fix type: Config-only | Code-only | Code + config})

{What was actually changed — not what should be changed, what WAS changed}

| # | Element/File | ID/Path | Change |
|---|-------------|---------|--------|
| 1 | {name}      | {id}    | {what changed} |

- {Bullet: additional changes not in table, e.g., RTDB cleanup, field reindexing}

{If fix deviated from RCA recommendation, add:}
**Deviation from RCA:** {what RCA recommended vs what was actually done, and why}

## 3. Expected Result

{Brief description of what the system should now do after the fix is applied}
{What the user/admin will see — concrete, testable outcomes}

## 4. Impact Area

> **QA** — areas to regression-test beyond the specific fix.
> **BA** — business workflows or pages affected by this change.

| Area | Impact | QA: What to Check | BA: What to Know |
|------|--------|-------------------|-----------------|
| {feature / page / module — e.g. "Death Certificate export"} | Direct fix | {specific thing to test} | {business workflow affected} |
| {adjacent feature — e.g. "Funeral form — Page 3"} | Regression risk | {what to verify is unchanged} | {why BA should be aware} |
| {unrelated area that shares the same config path or code} | May be affected | {spot check} | {low risk, but confirm with BA if unsure} |

## 5. Verification

**Dev:** Config confirmed in place as of {date}. {For code-only: commit {sha} deployed to dev.}

**QA Test Scenarios:**

| # | Scenario | Steps | Expected Result |
|---|----------|-------|-----------------|
| 1 | {scenario name} | {what QA should do step by step} | {what they should see} |
| 2 | {scenario name} | {steps} | {expected} |
| N | {regression check} | {steps} | {no regression — existing behavior unchanged} |

---

## UAT Deployment

> Fill in the block that matches your fix type. Delete the other two blocks.

---

### Config-only (no code deployment needed)

**Prerequisite:** Firebase write access to UAT environment

**ENV_SPECIFIC IDs — resolve before writing:**

| ID | How to find in UAT | Dev value |
|----|-------------------|-----------|
| `{RECORD_ID}` | In UAT: query `{parent_path}`, find the record where `{field}` = `"{value}"` | `{dev_id}` |

> Remove this table if all paths are STABLE (same across all environments).

**Steps:**
1. Resolve ENV_SPECIFIC IDs above (if any)
2. Dry-run — query each path to confirm current state matches expected
3. Apply config changes
4. Verify: {plain-language check in the app — e.g. "Open Funeral form, confirm field X shows Y"}

**Rollback:** Restore original values for each changed path (values listed in Fix section above)

---

### Code-only (no Firebase config changes)

**PR:** [{PR title}]({PR_URL}) — merged to `main`

**Steps:**
1. Confirm PR is merged to `main`
2. Deploy to UAT: {pipeline name / branch / manual step}
3. Verify deployment: {what to check — navigate to feature, confirm behavior}

**Rollback:** Revert PR

---

### Mixed — ⚠️ deploy code FIRST, then config

> Applying config before the code is deployed will cause incorrect behaviour.

**PR:** [{PR title}]({PR_URL}) — merged to `main`

**ENV_SPECIFIC IDs — resolve before writing:**

| ID | How to find in UAT | Dev value |
|----|-------------------|-----------|
| `{RECORD_ID}` | In UAT: query `{parent_path}`, find the record where `{field}` = `"{value}"` | `{dev_id}` |

> Remove this table if all paths are STABLE.

**Steps:**
1. Confirm PR is merged to `main`
2. Deploy code to UAT: {pipeline name / manual step}
3. Verify code is live: {what to check — e.g. "navigate to feature, confirm page loads"}
4. Resolve ENV_SPECIFIC IDs above (if any)
5. Dry-run — query each path to confirm current state
6. Apply config changes
7. Verify: {full app check — e.g. "complete the flow end-to-end, confirm correct output"}

**Rollback:** Revert PR for code changes. For config: restore original values (listed in Fix section above)

---

## 6. Not Addressed

| # | Item | Location | Reason | Follow-up |
|---|------|----------|--------|-----------|
| 1 | {what wasn't done} | {e.g., Page 3} | {why — separate concern, blocked, data unavailable} | {action — deferred to TICKET-KEY, will address in next sprint, needs BA clarification, etc.} |

## 7. Session Deploy

**Session deploy**
- dev: 382 — 2026-05-26 14:50 — RTDB
- uat: 419 — 2026-05-28 09:10 — RTDB
- prod: 437 — 2026-05-29 11:20 — Firestore

> One row per `apply` session from `session-log.md` (action=apply only — never revert / re-apply rows), chronological. Use these IDs to revert if the change needs to be backed out.
>
> **Format rules:** the canonical row-format spec lives in [short-template.md](short-template.md) (`{SESSION_ROWS}` field rules). In brief: list bullets only (NEVER a table), row shape `- {env}: {session_id} — {YYYY-MM-DD HH:MM} — {DB}`, the trailing `— {DB}` target database required, no timezone label on the timestamp, backticks around `{session_id}` optional. Keep the `**Session deploy**` heading exactly as written — it's the marker that activates the Output Guardian carve-out at `.claude/rules/output-guardian.md`.
