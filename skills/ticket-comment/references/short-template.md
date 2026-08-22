# Short Comment Template (opt-in progress checkpoint)

Use this template when `/ticket-comment` is invoked with the `--short` flag (or bare `short` token in args). The default — when no flag is passed — is the full template (`bug-template.md` / `feature-template.md`). SKILL.md Step 0b decides which template to render.

This comment is a progress checkpoint, not a QA handoff. It tells leaders / BA / PM / QA / the next deployer:

1. Which environment now carries the fix
2. Who should be aware (cc list)
3. The session identifiers needed to roll back if something goes wrong

Everything else (impact area, QA scenarios, BA verification, RCA link, deviation notes) waits for the full template.

**Typical usage:** the team posts SHORT after a dev or UAT apply (when QA isn't ready yet) and FULL after the prod apply (or whenever the comprehensive QA-handoff comment is needed). Nothing in this template enforces that pattern — it's the human convention, not a skill gate.

---

## Template body

```markdown
This {NOUN} is already in **{ENV_UPPER}**.

cc: {CC_LIST}

**Session deploy**
{SESSION_ROWS}
```

## Field rules

### `{NOUN}` — derived from Jira issue type

| Jira issue type | `{NOUN}` |
|---|---|
| Bug, Defect | `bug` |
| Story, Epic | `story` |
| Task, Sub-task, Improvement | `task` |
| Anything else | `ticket` |

Resolve in Step 0 (Read Jira ticket) — same payload as the full-template routing.

### `{ENV_UPPER}` — the env that was just applied to

`DEV` or `UAT`. Always uppercase. Derived from the most recent `apply` row in `tickets/{TICKET_KEY}/session-log.md` whose run-id matches the apply that triggered this comment. If the most recent apply was prod, do NOT use this template — route to the full template.

### `{CC_LIST}` — Jira mentions + literal role tail

Resolve at runtime from the Jira ticket payload already fetched in Step 0:

1. Fetch the ticket's `assignee` and `reporter` accountIds + display names.
2. Render each as a Jira-markdown mention (display name in plain text; the Atlassian MCP renders the @-mention from the accountId in the comment body).
3. Append the literal role tail: `BA / PM / QA`.

**Formatting:**
- Mention format: `@{Display Name}` (the Atlassian MCP comment body accepts `@accountId:{ACCOUNT_ID}` mention nodes — use whichever variant the host renders cleanly; default to the plain display-name string with an `@` prefix when accountId-node insertion is not available).
- Order: assignee first, reporter second, role tail last.
- Skip duplicates: if `assignee == reporter`, list them once.
- Skip empties: if `assignee` is null (unassigned ticket), drop it silently and surface `cc: @{Reporter}, BA / PM / QA`. If both are null, fall back to `cc: BA / PM / QA`.

**Mention style:** Both username-style (`@jordan.lee`) and display-name-style (`@Brendan Trestrail`) are accepted — pick whichever the Atlassian MCP returns for each accountId. The two styles can coexist in the same cc list (e.g. the assignee renders as `@jordan.lee` and the reporter renders as `@Brendan Trestrail`).

**Example:**
```
cc: @jordan.lee, @Brendan Trestrail, BA / PM / QA
```

### `{SESSION_ROWS}` — one row per `apply` session for this ticket

Build by reading `tickets/{TICKET_KEY}/session-log.md`:

1. Parse every `## Run N` block.
2. Keep only rows whose action is `apply` (drop `revert` and `re-apply` rows — per the leader-approved policy).
3. For each kept row, render exactly one markdown list bullet (NOT a table row):
   ```
   - {env}: {session_id} — {YYYY-MM-DD HH:MM} — {DB}
   ```
   - `{env}` is `dev` / `uat` / `prod`, lowercase.
   - `{session_id}` is the exact session id returned by `create_session`. **Backticks are optional**: for short numeric IDs (like `382`) write the bare value; for IDs containing dashes or alphanumerics that would otherwise look ambiguous in markdown (like `abc-456-xyz`), wrap in backticks.
   - `{YYYY-MM-DD HH:MM}` is the timestamp the run was applied. **No timezone label.** Do not append `(Sydney)`, `(UTC)`, `(local)`, or any parenthetical — the reader infers timezone from context. The timestamp comes verbatim from the `session-log.md` row.
   - `{DB}` is the **target database** written in that session — exactly one of `RTDB`, `Firestore`, or `RTDB+Firestore` (combined form when the session wrote to both). Derive it from the write tool recorded in the `session-log.md` row: `write_rtdb` → `RTDB`, `write_firestore` → `Firestore`. This field is required.
4. Order: chronological — earliest apply first, most recent apply last.

**Format rules — what NOT to do:**

- ❌ Do not render as a markdown table (`| Env | Session | Applied at (Sydney) |`). Tables add column-header noise; the list form is faster to scan.
- ❌ Do not add a timezone label to the timestamp. `2026-05-26 14:50` is correct; `2026-05-26 14:50 (Sydney)` is not.
- ❌ Do not wrap a 3-digit numeric session id in backticks; it reads as visual noise.
- ❌ Do not include the action column (`apply`) — the section heading already says "Session deploy", so every row is implicitly an apply.
- ❌ Do not drop the target-database field — every row must end with `— {DB}` (`RTDB` / `Firestore` / `RTDB+Firestore`).

**Example with one dev apply (first time `/ticket-comment` fires):**
```
- dev: 382 — 2026-05-26 14:50 — RTDB
```

**Example after uat apply (second time `/ticket-comment` fires; dev row carries forward):**
```
- dev: 382 — 2026-05-26 14:50 — RTDB
- uat: 419 — 2026-05-28 09:10 — RTDB
```

**Example with longer alphanumeric IDs (backticks recommended for clarity) and a Firestore target:**
```
- dev: `abc-456-xyz` — 2026-05-26 14:50 — Firestore
- uat: `def-789-rst` — 2026-05-28 09:10 — RTDB+Firestore
```

If `session-log.md` is missing or has zero `apply` rows, do NOT post the short comment — the rollback reference is the whole point of this shape, and a comment without it is misleading. Surface to the user: `No apply session found in session-log.md for {TICKET_KEY}. Run /apply-fix first, then re-run /ticket-comment.`

---

## Filled example (UAT apply, two prior runs)

```markdown
This bug is already in **UAT**.

cc: @jordan.lee, @Brendan Trestrail, BA / PM / QA

**Session deploy**
- dev: 382 — 2026-05-26 14:50 — RTDB
- uat: 419 — 2026-05-28 09:10 — RTDB
```

---

## What this template MUST NOT contain

- RCA link, Confluence URL, root-cause narrative — those live in the full template
- Impact Area table, QA test scenarios, regression checks
- BA "what to know" or "what to check" cells
- UAT Deployment block (config-only / code-only / mixed) — that's a full-template concern
- Deferred-item notes (full-template concern)
- Verification commands, code snippets, paths
- Anything that looks like a deploy plan

If the assembled comment grew beyond the four lines (headline + cc + "**Session deploy**" + N session rows), something's wrong — re-check the routing decision; you may want the full template instead.

## Output Guardian alignment

This template was designed with the Output Guardian carve-out at `.claude/rules/output-guardian.md`. The session IDs under `**Session deploy**` are the one approved exception — every other Output Guardian rule (no tool names, no AI attribution, no local artifact paths, no LLM voice) still applies inside this template body. The Step 5a linter enforces both the carve-out and the surrounding rules.
