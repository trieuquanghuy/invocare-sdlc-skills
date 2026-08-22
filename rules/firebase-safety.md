# Firebase Safety — Read-Only During Investigation

## Two Databases — Always Specify Which One

The project has **two separate Firebase databases**: Realtime Database (RTDB) and Firestore. Many paths look identical across both. Using the wrong one silently returns wrong data or writes to the wrong system.

**Every Firebase path reference — in queries, RCAs, specs, and deploy scripts — MUST state which database it targets:**

| Database | Query tool | Write tool | Notes |
|----------|-----------|------------|-------|
| Realtime Database | `query_rtdb` | `write_rtdb` | Most config, team settings, documents, events, clients |
| Firestore | `query_firestore` | `write_firestore` | Check ticket/evidence to confirm |

**Never assume.** If the ticket or evidence doesn't specify, query both as evidence discovery, then confirm the authoritative database from the ticket, schema, or owning application code. If the path exists in both databases or neither database, stop until corroborating evidence identifies the intended database; never choose one by convenience.

In rca.md evidence tables, always include a `DB` column: `RTDB` or `Firestore`.
In deploy.md write steps, always use the correct tool (`write_rtdb` vs `write_firestore`).

---

## Rule

Skills that investigate, query, or create documents **MUST NOT** write to Firebase RTDB or Firestore.

**Read-only skills (query only — NEVER write):**
- `create-rca` — investigation reads data, never modifies it
- `technical-investigation` — architecture research, never modifies data
- `create-spec` — reads current state to build the spec, never modifies it
- `doc-verification` — verifies data, never modifies it

**Write-permitted skills:**
- `apply-fix` — executes Firebase writes for any env (dev/uat/prod), with explicit user approval per write; promoting an applied fix to another env is just running it again against that env

## Why

Investigation must not alter the state being observed. A read during `create-rca` that accidentally triggers a write corrupts the evidence and could affect production data. All data changes must go through `apply-fix` with explicit per-step approval.

## Enforcement

If any investigation or spec-creation step requires verifying a value — use `query_rtdb` or `query_firestore` (read). Never call `write_rtdb`, `write_firestore`, `create_session`, `complete_session`, or any mutating operation outside of `apply-fix`.

---

## Central Running Log — Append on Every create_session

**Immediately after every `create_session` call** (before any writes), append one line to `sessions/running-log.md`. Create the file if it doesn't exist.

Format:
```
[DATE TIME] | [SESSION_ID] | [ENV] | [TICKET_KEY or "standalone"] | [action: apply/revert/re-apply/migration] | [brief description]
```

Example:
```
2026-04-23 14:32 | abc-123-xyz | dev | GEN-2759 | apply | Guardian Plan Agreement template fix
2026-04-23 15:10 | def-456-uvw | uat | standalone | migration | GEN-2759 dev→uat migration
```

This is the single source of truth for "what Firebase sessions were created in this Claude conversation" — any session audit or rollback tooling reads this file to find all session IDs without scanning every ticket folder.

---

## Session Logging — Mandatory After Every Write

After every Firebase write operation (`write_rtdb` or `write_firestore`), the session information **MUST** also be logged to `tickets/{TICKET_KEY}/session-log.md` (or `sessions/[DATE]-standalone.md` if not ticket-related).

**What to log (per run):**
- `session_id` returned by `create_session` — the only way to roll back without reconstructing old values manually
- Environment (`dev` / `uat` / `prod`)
- Date and time
- Action: `apply` / `revert` / `re-apply`
- Each path written and the operation used
- A field-minimized, redacted before-state record sufficient for rollback. Never paste raw query output; omit secret-looking values and unrelated fields.

**Why this is non-negotiable:** Without the `session_id`, rollback requires knowing the exact original values for every changed path. The session log is the only reliable source for this.

---

### Multiple runs (apply → rollback → re-apply)

The session-log.md is a **cumulative running log** — never overwrite it. Always append a new `## Run [N]` entry. Increment N from the last entry in the file.

Each run records its own action (`apply` / `revert` / `re-apply`) and its own `session_id`. Roll back overlapping runs in reverse chronological order. Before rolling back an older run, verify every affected path still matches that run's post-write state; if any path has changed, stop rather than overwrite later work.

---

### Running without local ticket context (teammate's script)

If you only have a `spec.md` or `deploy.md` (no local rca.md, no rollback.md, no existing ticket folder):

1. Create `tickets/{TICKET_KEY}/` if it doesn't exist
2. Apply the fix following the deploy.md steps
3. **Still create session-log.md** — this is your only rollback safety net in this scenario
4. State in the log: `Source: teammate's deploy.md — no local rca.md`

The session log must exist regardless of whether the rest of the ticket artifacts do.

Use the template at `.claude/skills/_shared/templates/session-log-template.md`.
