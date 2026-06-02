---
name: summarize-firebase-session
description: "Use when you want a summary of all Firebase operations run in the current Claude session — across multiple tickets, rollbacks, or standalone runs. Triggers on: summarize session, what did I run today, log firebase session, session summary, what was applied."
argument-hint: "Optional: date or folder (e.g. 2026-04-23 or tickets/GEN-2759)"
disable-model-invocation: true
---

# Summarize Firebase Session

Collects all Firebase session IDs logged during the current Claude session, calls `validate_session_rollback` for each, and produces a combined summary saved to `sessions/`.

**Output guardian:** all output reads as written by a developer. Apply `.claude/rules/output-guardian.md` — never include tool names, session IDs in user-facing prose (the audit table is the only place a session_id should appear), or any indication of automation.

Useful when:
- You ran multiple apply-fix or migration runs across different tickets
- You did rollbacks and re-applies
- You want a full audit of what changed in Firebase today
- The changes are not tied to a single ticket

---

## NOT This Skill If

- User wants the status of a single ticket → use `/task-status {KEY}` (it reads the per-ticket `session-log.md` as part of its status card).
- User wants to verify whether Firebase writes still hold in the live DB → use `/task-status` (config drift check).
- User wants the summary posted to Jira / Confluence — this skill writes a local summary file only.

---

## Step 1: Collect Session IDs

**Primary source — `sessions/running-log.md`:**

Every `create_session` call appends one line here automatically (per `firebase-safety.md` global rule). Read this file first.

```
sessions/running-log.md
```

Filter by date (today by default, or the date argument provided). Each line:
```
[DATE TIME] | [SESSION_ID] | [ENV] | [TICKET_KEY or "standalone"] | [action] | [description]
```

**Always run a sanity diff** — even when `running-log.md` exists. Scan `tickets/*/session-log.md` for entries matching the date and compare:

| running-log entry count | tickets/*/session-log entry count | Action |
|-------------------------|-----------------------------------|--------|
| Equal | Equal | ✓ no drift, proceed silently |
| Greater | (running-log has more) | Possible orphaned session — flag and continue |
| Less | (per-ticket logs have more) | ⚠️ One or more sessions skipped the running-log append. Surface the missing IDs to the user before proceeding. |

The drift case usually means a skill aborted between `create_session` and the running-log append, or an old run pre-dated the running-log requirement. Either way, the per-ticket session-log entries are authoritative for "what was actually written" — incorporate them into the summary and note the drift.

**If running-log.md is missing entirely:** fall back to per-ticket scan and ask the user to confirm.

Build a consolidated list:
| Session ID | Source ticket | Environment | Action | Date/Time |
|-----------|--------------|-------------|--------|-----------|
| `[SID]` | [TICKET_KEY or "standalone"] | dev / uat / prod | apply / revert / re-apply | [DATE TIME] |

---

## Step 2: Validate Each Session

For each session ID, call:

```
validate_session_rollback(session_id: "[SESSION_ID]")
```

This returns the exact paths and values the session changed.

Record for each session:
- **DB type** per path (RTDB or Firestore)
- **Paths written** with operations (create / update / delete)
- **Values** (before state if available from session-log.md, after state from validate)
- **Status**: completed / rolled back / unknown

If `validate_session_rollback` returns an error (session expired or unavailable), note: `SESSION UNAVAILABLE — data from session-log.md only`.

### Confirm final state against the live DB (read-only)

The records above are **reconstructed history** — `validate_session_rollback` output plus the before-values captured in `session-log.md`. They describe what each session *intended* to write, not what the DB holds right now. To confirm the actual current state, read each final path back:

- For each distinct path that has a final write, run a **read-only** query against the database that path targets (per `firebase-safety.md`, every path states which DB it belongs to):
  - RTDB path → `query_rtdb(path: "{PATH}", environment: "{ENV}")`
  - Firestore path → `query_firestore(...)` for that path
- This is read-only verification only. **Never** call `write_rtdb`, `write_firestore`, `create_session`, `complete_session`, or `rollback_session` here — this skill is read-only (`firebase-safety.md`).

Keep the **confirmed live value** distinct from the **reconstructed history**: the history shows what the session wrote; the live read shows what the DB returns today. If they differ (e.g. a later out-of-band edit), surface it as drift in the summary rather than overwriting one with the other.

---

## Step 3: Deduplicate and Summarize

If the same path was written multiple times across sessions:
- Show the **full history** (each write in order)
- Mark the **final state** (last write to that path)
- Flag paths that were written then rolled back (net effect = no change)

**Large values:** when a path's value JSON is large (more than a few lines — e.g. a full form/template object), do NOT paste the whole value inline in the summary table. Save it to a file under `sessions/content/` (e.g. `sessions/content/[DATE]-[short-path-slug].json`) and reference that file from the table (path + a one-line description), keeping the table skimmable. Inline only small scalar values.

---

## Step 4: Save Summary

Read [session-summary-template.md](./references/session-summary-template.md).

Save to: `sessions/[DATE]-[ENV]-summary.md`
(e.g. `sessions/2026-04-23-dev-summary.md`)

Create the `sessions/` folder if it doesn't exist.

---

## Quality Bar

- [ ] All session IDs from today's session-log.md included
- [ ] Sanity diff run between running-log.md and per-ticket session-log entries — drift surfaced if any
- [ ] `validate_session_rollback` called for every available session ID
- [ ] DB type noted per path
- [ ] Paths written then rolled back flagged as "net no change"
- [ ] Final state shown for each path
- [ ] Final state confirmed against the live DB with a read-only `query_rtdb` / `query_firestore` (correct tool per DB), kept distinct from reconstructed history; live-vs-history drift surfaced
- [ ] Large value JSON saved to `sessions/content/` and referenced from the table, not pasted inline
- [ ] Unavailable sessions noted explicitly

## Next step

After completing this skill, print this block to the user before ending.

```
---
**Next step**

If a session needs rollback, pull the session_id from the summary and use the rollback validation tooling.

Otherwise: you're done. Summary is logged for audit.
---
```
