## IMPORTANT RULES (remove this section before saving):
- Apply the fix to {ENV} BEFORE running these checks
- Confirm DB state before running UI scenarios — a passing UI test on wrong DB data is a false positive
- Write steps at UI level — specific enough for a QA or dev who did NOT write the fix to follow
- Every step must name: the exact URL or screen, the exact element to click, the exact value to enter
- Every step must have its own expected result
- Minimum: 1 happy path + 1 edge case + 1 regression check
- Use real entity IDs and real URLs for the target environment
- **Coverage is the gate:** every AC (story) or every reported symptom + its regression surface (bug) maps to at least one scenario in the Coverage table. One scenario MAY cover several ACs — map them all to it; do NOT pad one scenario per AC when one flow proves three. An AC that cannot be tested yet gets a NOT COVERED row with the reason (e.g. blocked on data) — visible, never silently dropped.
- **Proportionality:** scenarios prove the ACs, nothing more. No scenarios for behavior no AC or symptom names, no duplicate scenarios proving the same thing from a different angle, no speculative edge cases beyond the one the template requires.

---

# [TICKET_KEY]: Validation Guide

**Ticket:** [TICKET_KEY] — [JIRA_TITLE]
**Target environment:** dev | uat
**Fix must be applied before starting.**
**Estimated time:** ~[N] minutes

---

## Pre-Condition: Confirm Fix Is Applied

Before running any UI scenario, verify the fix actually landed in the database.

**Environment:** `{ENV}`

Run this check against every path changed by the fix:

**Database:** RTDB | Firestore
**Path:** `[exact path]`
**Query:** `[exact read-only verification command]`

Expected value:
```
[exact value the fix wrote]
```

If the DB does NOT show the expected value → **stop. The fix has not been applied. Run `/apply-fix [TICKET_KEY]` first.**

---

## Login & Access

| Field | Value |
|-------|-------|
| URL | `[APP_URL_FOR_ENV]` |
| Login as | [role — e.g. "admin user for [TEAM_NAME] team"] |
| Team context | [TEAM_NAME] — ID: `[teamId]` |

> If the fix is backend-only (e.g. API behavior, Cloud Function logic) with no UI surface, replace this section with the API contract being verified (endpoint, request, expected response) and skip the UI scenarios below. Use the DB state checks as your primary validation instead.

## Test Data

| Type | Identifier | URL (if any) | Notes |
|------|-----------|--------------|-------|
| [client / event / form / template / team config / etc.] | `[ID, name, or path]` | `[URL or "—" if backend]` | [what this record represents and why it's used] |

---

## Coverage

> One row per acceptance criterion (story) or reported symptom + regression surface (bug). Every row maps to ≥1 scenario; a scenario may appear in several rows. NOT COVERED rows carry the reason.

| # | AC / Symptom | Covered by | Notes |
|---|--------------|------------|-------|
| AC1 | [text] | Scenario 1 | |
| AC2 | [text] | Scenario 1, 3 | one flow proves both |
| AC3 | [text] | NOT COVERED | [reason — e.g. blocked on NZ data] |

---

## Scenario 1: Happy Path — [main requirement from ticket]

**Goal:** [One sentence on what this scenario proves]

**Preconditions:**
- Logged in as [role]
- Fix confirmed applied (Pre-Condition check passed)
- On screen: [page name or URL]

| Step | Action | Expected Result | ✓/✗ |
|------|--------|-----------------|-----|
| 1 | Navigate to `[URL]` | Page loads, showing [what] | |
| 2 | Click **[Button/Link name]** | [What happens] | |
| 3 | Select **[Option]** from **[Field]** | [Option is selected] | |
| 4 | Click **[Button]** | [File downloads / success message / redirect] | |
| 5 | [Verify the output] | [Exact expected content] | |

**Overall Result:** [ ] Pass / [ ] Fail
**Notes:** ___

---

## Scenario 2: [Edge Case — e.g. missing data, fallback behavior]

**Goal:** [What this scenario proves]

**Preconditions:**
- [Any different setup — e.g. "Use entity `[entityId2]` which has no [field]"]

| Step | Action | Expected Result | ✓/✗ |
|------|--------|-----------------|-----|
| 1 | Navigate to `[URL]` | [Expected] | |
| 2 | [Action] | [Expected result] | |
| 3 | [Trigger the edge case] | [Expected fallback — e.g. "Shows 'N/A' instead of crashing"] | |

**Overall Result:** [ ] Pass / [ ] Fail
**Notes:** ___

---

## Scenario 3: Regression Check — [adjacent feature that could be affected]

**Goal:** Confirm the fix did not break [adjacent feature].

**Preconditions:**
- [Setup]

| Step | Action | Expected Result | ✓/✗ |
|------|--------|-----------------|-----|
| 1 | Navigate to `[URL of adjacent feature]` | [Expected — same as before fix] | |
| 2 | [Action that exercises the adjacent feature] | [Expected — unchanged behavior] | |

**Overall Result:** [ ] Pass / [ ] Fail
**Notes:** ___

---

## Post-Fix DB State Confirmation

After all scenarios pass, re-query to confirm DB state is stable (no unexpected side effects):

**RTDB:**
```
query_rtdb(environment_name: "{ENV}", path: "[PATH_CHANGED_BY_FIX]")
```

**Firestore:**
```
query_firestore(environment_name: "{ENV}", path: "[PATH_CHANGED_BY_FIX]")
```

Expected: same as Pre-Condition check — `[expected value]`

---

## Sign-Off

| Environment | Pre-Condition DB Check | All Scenarios Pass | Signed Off By | Date |
|-------------|----------------------|-------------------|---------------|------|
| dev | [ ] | [ ] | | |
| uat | [ ] | [ ] | | |
