## IMPORTANT RULES (remove this section before saving):
- This file is written by apply-fix AT RUNTIME — not at spec creation time
- Append a new entry for EVERY action: apply, revert, re-apply, migration
- Session ID is the most important field — it enables `rollback_session()` without needing old values
- Capture current state BEFORE each write (the calling skill already queries this) — paste it here
- For deferred sprints: record the revert run so the next developer knows the fix was intentionally held
- For migrations: record source env, target env, and ID remappings used

---

# [TICKET_KEY]: Session Log

**Ticket:** [TICKET_KEY] — [JIRA_TITLE]
**Target Sprint:** Sprint [N]

---

## Run [N] — [ENV] — [DATE TIME]

**Action:** apply | revert | re-apply | migration
**Reason:** [e.g. "dev testing for Sprint 3 — will revert after validation" | "reverting — hold until Sprint 3" | "Sprint 3 permanent apply" | "dev→uat promotion"]
**Sprint:** Sprint [CURRENT]
**Session ID:** `[SESSION_ID_RETURNED_BY_CREATE_SESSION]`
**Environment:** dev | uat | prod
**By:** [WHO_RAN_THIS]
**Fix type:** config | code | mixed
**Pre-flight:** PASS | WARN (acknowledged: R7, R8) | SKIPPED (reason: <text>)

### Migration metadata (only for action: migration)

**Source env:** dev | uat
**Target env:** uat | prod
**ID remappings:**

| Source path | Target path | Match field |
|-------------|-------------|-------------|
| `[/documents/-ABC123/...]` | `[/documents/-XYZ456/...]` | name = "Standard Death Certificate" |

### Writes Executed

| # | Path | DB | Operation | Result |
|---|------|----|-----------|--------|
| 1 | `[path]` | RTDB / Firestore | create / update_partial / delete | ✓ / ✗ |

### State Before This Action (captured at apply time)

**[path queried before write]:**
```json
[paste query_rtdb / query_firestore result here — this is the state BEFORE this run]
```

### Undo This Run

**Preferred — session rollback:**
```
validate_session_rollback(session_id: "[SESSION_ID]")
```
Then:
```
rollback_session(session_id: "[SESSION_ID]")
```

**If session unavailable**, use the rollback steps in `spec.md` (Option B) with the "State Before This Action" above.

---
<!-- append next run below this line -->
