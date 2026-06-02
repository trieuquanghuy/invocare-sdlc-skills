## IMPORTANT RULES (remove this section before saving):
- Summary: write enough that someone reading spec.md without rca.md understands what is broken, who is affected, and what this spec changes
- Technical Approach: explain WHY the fix works — before/after state, caveats, risks
- All Firebase paths must come from rca.md evidence — never invent
- Data blocks must contain real values — no [PLACEHOLDER] in data fields
- Read actual code files before writing code sections — use exact current code
- Use {ENV} for environment names so this spec is reusable for dev and UAT
- Dry-run queries must verify state BEFORE each write — not just confirm after
- Use `query_rtdb` / `write_rtdb` for Realtime Database paths; `query_firestore` / `write_firestore` for Firestore paths
- If Target Sprint is in the future, Status starts as "on-hold" — apply to dev for testing, then revert until that sprint

---

# [TICKET_KEY]: Fix Specification

**Ticket:** [[TICKET_KEY]]([JIRA_URL]/browse/[TICKET_KEY]) — [JIRA_TITLE]
**RCA:** [tickets/[TICKET_KEY]/rca.md](rca.md)
**Fix Type:** config | code | mixed
**Target Sprint:** Sprint [N]
**Status:** on-hold | ready-to-apply | applied-dev | applied-uat | applied-prod
**Environments:** dev → uat → prod (replace `{ENV}` at apply time)

---

## Summary

[1–2 paragraphs readable without opening rca.md:
- What is broken and for whom (specific feature, form, export, user group)
- What this spec changes and the expected outcome after applying it]

## Root Cause

**Classification:** CONFIGURATION_GAP | CODE_DEFECT | DATA_MAPPING_GAP

[1 paragraph: technical explanation of why the issue occurs — exact path, field, or value that is wrong and why it causes the symptom]

## Technical Approach

### What is being changed
[Specific paths, files, or templates being modified. Be concrete — name the field, the path, the function. Avoid vague phrasing like "fix the config" without saying which config.]

### Why this fixes the root cause
[Cross-reference the root cause from rca.md. Explain the causal link: current state X causes symptom Y; changing X to Z eliminates Y because [mechanism].]

### Before / after state
**Before:** [concrete value, e.g. `filename: 'foo.pdf'`]
**After:** [concrete value, e.g. `filename: 'bar.pdf'`]

### Risks and caveats
[At least one stated risk OR an explicit "no risks" with justification. Mention what's outside the change set (e.g. "this does not change rendering of existing forms"). Note any shared paths and which other features use them.]

## Changes

| # | Change | DB | Target | Notes |
|---|--------|-----|--------|-------|
| 1 | [description] | RTDB / Firestore | [path or file] | [shared path / caveats if any] |

---

## Environment Mapping

> Before deploying to any environment, check this table. `STABLE` paths are identical across dev/UAT/prod. `ENV_SPECIFIC` paths contain auto-generated IDs that differ per environment — **resolve them before executing any writes**.

| # | Path segment | Stability | Dev value | How to find in target ENV |
|---|-------------|-----------|-----------|--------------------------|
| 1 | `[full path or the varying ID segment]` | STABLE | `[value]` | Same across all environments |
| 2 | `[parent_path/{RECORD_ID}/child]` | ENV_SPECIFIC | `[dev_record_id]` | See lookup below |

### Lookup: [RECORD_ID] — ENV_SPECIFIC

To find the equivalent record in the target environment:

```
query_rtdb(
  environment_name: "{ENV}",
  path: "[parent_path]"
)
```

Find the record where `[field]` == `"[exact value from dev — e.g. label, name, type]"`.
Use that key as `{RECORD_ID}` in all write steps below.

Dev confirmed: `{RECORD_ID}` = `[dev_value_for_reference]`

[Repeat one Lookup block per ENV_SPECIFIC ID. Remove this section entirely if all paths are STABLE.]

---

## Deployment Plan

| Step | Action | When | Notes |
|------|--------|------|-------|
| 1 | Apply to dev | Sprint [CURRENT] — for testing only | Revert after validation |
| 2 | Revert from dev | Sprint [CURRENT] — after validation passes | Hold until target sprint |
| 3 | Re-apply to dev | Sprint [N] begin | Permanent apply |
| 4 | Apply to UAT | Sprint [N] — after dev sign-off | |
| 5 | Apply to prod | Sprint [N] — after UAT sign-off | |

> **If this is a same-sprint fix**, delete the Deployment Plan table and apply directly.

---

## Execution

> Replace `{ENV}` with `dev` or `uat` at apply time.
> Database per path: use `query_rtdb`/`write_rtdb` for RTDB, `query_firestore`/`write_firestore` for Firestore.

### Dry Run — verify state before writing

> If any path is `ENV_SPECIFIC` (see Environment Mapping above), resolve the correct ID for `{ENV}` before running these queries.

Run these queries **before** any writes. If results differ from expected, stop and re-check rca.md.

**Check [what you're verifying] ([DB type]):**
```
query_rtdb(
  environment_name: "{ENV}",
  path: "[EXACT_PATH_FROM_RCA]"
)
```
Expected: [what the current value should look like before the fix]
If different: [what that would mean — when to stop vs when to continue]

---

### Live Execution

**Step 1: Create session**
```
create_session(
  environment_name: "{ENV}",
  description: "[TICKET_KEY]: [brief description]"
)
```
Save the returned `session_id` — required for all writes and for rollback.

---

**Step [N]: [Change description] — [DB type]**
> ⚠️ ENV_SPECIFIC: resolve `{RECORD_ID}` from Environment Mapping before executing. [Remove this line if path is STABLE.]
```
write_rtdb(
  environment_name: "{ENV}",
  session_id: "<SID>",
  allow_writes: true,
  path: "[EXACT_PATH_FROM_RCA]",
  operation: "create | update_partial | update_full | delete",
  data: {
    [exact field]: [exact value]
  }
)
```
Why: [one sentence on what this achieves]

[Copy the correct block above for each write. Use write_rtdb for RTDB paths, write_firestore for Firestore paths. Add/remove the ⚠️ ENV_SPECIFIC note per step.]

---

**Step [N+1]: Complete session**
```
complete_session(session_id: "<SID>")
```

---

### Code Changes

> Only include this section for `code` or `mixed` fix types. Remove for config-only fixes.
> For multi-file fixes: repeat the File / Repo / Current code / Fix block below per file.

**File:** `[path/to/file]` (line ~[N])
**Repo:** [REPO_NAME]
**Callers / blast radius:** [summary from search_with_context — direct callers count, services affected]

Current code (read from file — exact):
```[language]
[CURRENT_CODE_AS_READ_FROM_FILE]
```

Fix:
```[language]
[CORRECTED_CODE]
```
Why: [one sentence]

---

## Rollback

**Use when:** the fix caused a regression or must be undone in `{ENV}`.

**Do NOT delete:** `[shared_path]` — [reason: used by other features. Remove this line if no shared paths.]

### Option A: Session Rollback (preferred)

Requires the `session_id` from `tickets/[TICKET_KEY]/session-log.md`.

```
validate_session_rollback(session_id: "[SESSION_ID_FROM_SESSION_LOG]")
```
Review output — confirm it only undoes what you expect.

```
rollback_session(session_id: "[SESSION_ID_FROM_SESSION_LOG]")
```

Verify after rollback:
```
query_rtdb(environment_name: "{ENV}", path: "[PATH_THAT_WAS_CHANGED]")
```
Expected after rollback:
```
[paste original value from rca.md evidence]
```

### Option B: Manual Rollback (fallback — session unavailable)

> Use only when the session_id is no longer valid or session-log.md is missing.
> For fixes with multiple writes: repeat Steps 3 (revert) per write, in REVERSE order from the original apply. Step 4 (complete session) runs once at the end.

**Step 1: Capture current broken state before writing**
```
query_rtdb(environment_name: "{ENV}", path: "[PATH_TO_REVERT]")
```
If result already matches the original — rollback may already be done. Stop and verify.

**Step 2: Create rollback session**
```
create_session(
  environment_name: "{ENV}",
  description: "[TICKET_KEY]: Manual Rollback"
)
```

**Step 3: Revert [change description]**
```
write_rtdb(
  environment_name: "{ENV}",
  session_id: "<SID>",
  allow_writes: true,
  path: "[EXACT_PATH_THAT_WAS_CHANGED]",
  operation: "delete | update_full",
  data: {
    [original field]: [original value — exact, from rca.md evidence]
  }
)
```

**Step 4: Complete session**
```
complete_session(session_id: "<SID>")
```

---

## Acceptance Criteria

- [ ] [Specific testable outcome — not vague]
- [ ] [Second testable outcome]
- [ ] Regression: [adjacent area to verify hasn't broken]
