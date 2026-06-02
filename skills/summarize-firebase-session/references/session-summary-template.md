## IMPORTANT RULES (remove before saving):
- Fill every section from validate_session_rollback results
- Note DB type (RTDB / Firestore) per path
- Flag any path that was written then rolled back as "net no change"
- SESSION UNAVAILABLE = session expired, use session-log.md data only

---

# Firebase Session Summary — [DATE]

**Environment:** dev | uat | prod
**Sessions covered:** [N]
**Generated:** [DATE TIME]

---

## Sessions Run

| # | Session ID | Ticket | Action | Environment | Status |
|---|-----------|--------|--------|-------------|--------|
| 1 | `[SID]` | [TICKET_KEY or standalone] | apply / revert / re-apply | dev / uat | completed / rolled back |

---

## Changes by Path

| # | DB | Path | Net Effect | History |
|---|-----|------|-----------|---------|
| 1 | RTDB | `[path]` | ✅ Applied / ↩️ Rolled back / ⚠️ No change | Run 1: set X → Run 2: reverted |

---

## Detail

### Path 1: `[path]` — RTDB / Firestore

**Net effect:** Applied / Rolled back / No change (written then reverted)

| Run | Session | Action | Value set |
|-----|---------|--------|-----------|
| 1 | `[SID]` | update_partial | `{ field: value }` |
| 2 | `[SID]` | rollback | `{ field: original_value }` |

**Final state:**
```json
{ "field": "current_value" }
```

*(Repeat for each path)*

---

## Unavailable Sessions

| Session ID | Reason | Data source |
|-----------|--------|-------------|
| `[SID]` | Session expired | session-log.md only — values may be incomplete |

---

## Notes

[Any observations — e.g. "GEN-2759 was applied twice; second run overwrote the first", "Rollback on Run 2 restored original state"]
