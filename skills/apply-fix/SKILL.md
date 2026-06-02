---
name: apply-fix
description: "Use when ready to execute an approved fix (config or code) in dev / uat / prod — after spec.md or deploy.md has been reviewed. Trigger on: apply fix, execute fix, deploy fix, run deploy script, apply spec for GEN-XXXX. Append --dry-run to simulate without writes."
argument-hint: "Jira ticket key (e.g. GEN-1662) and environment (dev|uat|prod). Append `--dry-run` to simulate without executing writes."
disable-model-invocation: true
---

# Apply Fix

Execute an approved fix specification across `dev` / `uat` / `prod`. For config fixes, runs Firebase writes step-by-step with your approval at each write. For code fixes, applies code changes. Every run — real or dry — produces a structured `deploy-result.md` ledger under the ticket folder.

This skill is the canonical apply path.

**Output guardian:** all output reads as written by a developer. Apply `.claude/rules/output-guardian.md` — never include tool names, session IDs, or any indication of automation.

**Git safety:** apply `.claude/rules/git-safety.md` — refuse on dangerous git states, no destructive flags, no diff cruft.

**Agent safety:** apply `.claude/rules/agents-safety.md` — the pre-flight checker subagent (Step 2) is read-only, returns structured JSON, escalates failures.

## NOT This Skill If

- User hasn't generated a `spec.md` or `deploy.md` yet → use `/create-spec` first.
- User wants to investigate the issue before fixing → use `/create-rca`.
- User wants to open a PR for committed code without any Firebase writes → use `/create-pr`.

---

## Prerequisites

- At minimum: a deploy.md or spec.md file — in **any location, with any filename**
- You must explicitly approve each step before it executes

## Step 1: Locate and Read the File

The file may be anywhere — `tickets/GEN-XXXX/deploy.md`, `~/Downloads/fix-script.md`, `~/Desktop/GEN-2759-deploy.md`, or any path the user provides.

**Step 1a: Identify the ticket key**

Look for a ticket key (`GEN-XXXX`, `FIR-XXXX`, `IVC-XXXX`) in:
1. The filename (e.g. `GEN-2759-deploy.md`)
2. The first few lines of the file (e.g. `**Ticket:** GEN-2759`)
3. If not found → ask: "What ticket key is this for? (needed for session log)"

**Step 1b: Copy to standard location if needed**

If the file is NOT already at `tickets/{TICKET_KEY}/`, copy it there before proceeding. The standard name depends on the target env (the `prepare-uat` skill emits the env-specific UAT filename so the UAT plan can sit alongside a dev `deploy.md` without colliding):

| Target env | Standard filename |
|---|---|
| `uat` | `tickets/{TICKET_KEY}/{TICKET_KEY}-deploy-uat.md` |
| `dev` / `prod` (or env not yet known) | `tickets/{TICKET_KEY}/deploy.md` |

If the source file is `spec.md`, copy it to `tickets/{TICKET_KEY}/spec.md` regardless of env.

This keeps session-log.md alongside the artifact. Note in session log: `Source: [original file path]`.

**Step 1c: Determine what is available and read it**

Resolve the deploy file in this order (the `prepare-uat` skill writes an env-specific filename for UAT plans; everything else uses the plain `deploy.md`):

1. If target env is `uat` AND `tickets/{TICKET_KEY}/{TICKET_KEY}-deploy-uat.md` exists → use that file as the execution source.
2. Else if `tickets/{TICKET_KEY}/deploy.md` exists → use that file.
3. Else fall back to `spec.md`.

If both `{TICKET_KEY}-deploy-uat.md` AND `deploy.md` exist and target env is `uat`, prefer the env-specific file and tell the user: `Using {TICKET_KEY}-deploy-uat.md (env-specific) — deploy.md is also present but ignored for this run.` Never silently merge them.

| Available | Action |
|-----------|--------|
| `spec.md` + `deploy.md` (or `{TICKET_KEY}-deploy-uat.md`) | Read spec.md for context, follow the deploy file for execution |
| Deploy file only | Read it directly — it is the execution source |
| `spec.md` only | Read spec.md — follow Execution section for config writes, Code Changes section for code |
| Non-standard filename | Read it, copy to the standard name under `tickets/{TICKET_KEY}/` (`{TICKET_KEY}-deploy-uat.md` for env=uat, `deploy.md` otherwise) |

Identify:
- Fix type: config / code / mixed
- Database per path: RTDB or Firestore (from `write_rtdb`/`write_firestore` calls)
- Environment(s) to target
- Number and scope of changes
- **Code-dependency notice** — any "Code change (out of scope for this file)" block in the deploy file. Capture verbatim for Step 3.

**Step 1d: Resolve run mode**

Detect `--dry-run` in `$ARGUMENTS`:
- Present → run mode is `DRY-RUN`. No `create_session`, no `write_*`, no `complete_session`, no `running-log.md` or `session-log.md` mutations. Step 4f still produces `deploy-result.md` tagged `DRY-RUN SIMULATION`.
- Absent → run mode is `REAL`. Full apply path.

## Step 2: Pre-flight check

Before any writes or edits, validate inputs by dispatching the pre-flight checker subagent.

1. Read `./checker-prompt.md` from this skill folder.
2. Dispatch a `pipeline-checker` subagent (`.claude/agents/pipeline-checker.md`) with:
   - The full prompt from `checker-prompt.md`
   - Ticket key (from Step 1a)
   - Target env (from the `/apply-fix` arg)
   - Paths: `tickets/{TICKET_KEY}/rca.md` (if exists), `tickets/{TICKET_KEY}/spec.md` (if exists), the deploy file resolved in Step 1c (`{TICKET_KEY}-deploy-uat.md` for env=uat, otherwise `deploy.md`), `tickets/{TICKET_KEY}/session-log.md` (if exists)
3. Parse the JSON result block from the subagent's reply per `.claude/skills/_shared/contracts/checker-contract.md`: `{ verdict, ticket_key, target_env, summary, iteration_hint, gaps[] }`.
4. Partition `gaps[]` by severity. Branch on verdict:
   - **FAIL** → print every gap with `severity: blocker` as shown below, exit. No `create_session` call. No writes happen.
   - **WARN** → print every gap with `severity: warning`, ask `Proceed anyway? (yes/no)`. If `no` → exit. If `yes` → record acknowledged warning rule IDs (e.g. `R7, R8`) for Step 4d's session-log entry, continue.
   - **PASS** → print `severity: info` gaps (if any), continue silently otherwise.

Format each gap entry as:
```
[<rule>] <issue>
  Resolve: <suggested_fix>
  Evidence: <evidence>     ← only if present
```

If the checker dispatch fails or returns malformed JSON: print `Pre-flight could not run: <reason>. Without pre-flight, no automated input validation.` Then ask `Proceed without pre-flight? (yes/no)`. **For target env = prod** the prompt instead requires the user to type the exact phrase `proceed without pre-flight` (no plain `yes`). Whatever the user does, capture `Pre-flight: SKIPPED (dispatch failure: <reason>)` for Step 4d's session-log entry.

This pre-flight runs ONCE per `/apply-fix` invocation — it does not iterate. The Quality Bar / rubric the checker enforces lives in `./checker-prompt.md`. Keep them in sync per the source line at the top of that file.

---

## Step 3: Confirm Before Starting

**Step 3a: Code-dependency pre-flight (uat / prod only)**

If target env is `uat` or `prod` AND Step 1c captured a "Code change (out of scope for this file)" notice, surface it and ask the user explicitly:

> The deploy plan declares the following code dependencies must already be live on `{ENV}`:
> {paste the notice verbatim}
>
> Have these been deployed and verified on `{ENV}`? (yes / no)

If `no` → stop. Do not proceed until code deploys are confirmed.

For `dev` runs this step is skipped — dev is the testbed; nothing else is expected live there.

**Step 3b: Summary confirmation**

Summarize what you're about to do:

```
About to apply fix for {TICKET_KEY}:
- Fix type: {config | code | mixed}
- Environment: {dev | uat | prod}
- Mode: {REAL | DRY-RUN}
- {N} Firebase writes / {N} code files to change
- Code dependencies confirmed live: {yes | n/a — dev}

Proceed? (yes / no)
```

Wait for explicit confirmation. If the fix targets **production** AND mode is `REAL`, add a prominent warning:

> ⚠️ **PRODUCTION FIX** — this will modify live data. Confirm: yes

## Step 4: Config Fix — Execute Firebase Writes

**Sub-step dataflow:**

```
once per run                          per write (loop)                    once per run
─────────────────────────             ───────────────────────────         ──────────────────
4a   create session (REAL)            4b.i   pre-write read               4c   complete session (REAL)
4a.5 running-log append (REAL)        4b.ii  drift check                  4d   write session log (REAL)
4b.0 resolve template artifacts ──┐   4b.iii substitute + approve + write 4e   run verification
                                  │   4b.iv  sibling-fields check         4f   write deploy-result.md
                            artifact_map                                  4g   output guardian on deploy-result
                                                                          4h   upload deploy-result to Drive (REAL + uat/prod, opt-in)
                                                                          4i   re-upload drifted artifacts (REAL, conditional)
```

Pre-write reads (4b.i) and the per-write preview + approval (4b.iii) run in BOTH modes — they're how dry-run gathers material for Step 4f's report.

---

> Throughout Step 4 (and the Rules / Quality Bar below), "deploy.md" means **the deploy file resolved in Step 1c** — that is `{TICKET_KEY}-deploy-uat.md` when target env is `uat` and the env-specific file is present, otherwise `deploy.md`.

> **Run-mode gating:** Sub-steps 4a, 4a.5, 4c, and 4d are **REAL-mode only**. On dry-run, skip them — never create a session, never call `write_*`, never touch `sessions/running-log.md` or `tickets/{TICKET_KEY}/session-log.md`. Pre-flight reads (4b's drift check) and the per-write display + approval are always run; they're how the dry-run gathers material for Step 4f's report.

**Consult the DB map first.** Check whether `.claude/skills/_shared/references/firebase-db-map.md` exists.

**If the map file does NOT exist:** skip the consult/staleness/append logic and fall back to pre-map behavior — for every write, confirm the DB type from the deploy plan itself; if the plan doesn't state it, query both `query_rtdb` and `query_firestore` against the target path during 4b.i pre-flight to determine which holds the data, and pick the matching write tool. Print a one-line note: `Note: firebase-db-map.md not found; falling back to per-path probe before each write.` Continue with Step 4 as normal.

**If the map file exists:** for every write in the deploy plan, cross-check its path against the map before choosing the tool. First, glance at its `Last refreshed:` header — if the date is >60 days old, ask the user `The Firebase DB map was last refreshed {DATE} ({N} days ago); refresh before applying? (yes/no)` and only proceed after confirmation (stale maps are a real risk when writes are about to hit prod / uat). If the path is listed, use the stated DB (`write_rtdb` vs `write_firestore`) — and flag any mismatch with what the deploy plan says as a Drift / Plan inconsistency under Step 4f Notes. If the path is NOT listed, query both DBs in the pre-flight read (4b.i) to confirm which one holds it, then append a row to the `## Discovered paths` section of the map (`path | DB | first-seen | last-verified | source: {TICKET_KEY}`).

Follow the deploy file steps in order. For EACH write:

### 4a. Create Session (once) — REAL only

```
create_session(
  environment_name: "{ENV}",
  description: "{TICKET_KEY}: {brief description}"
)
```

Save the session_id for all subsequent writes. **Skip on dry-run** — use the placeholder `sim-{ENV}-{TICKET_KEY-lower}-{YYYYMMDD}` in Step 4f's report.

### 4a.5. Append Running Log — REAL only

**Immediately** after `create_session` returns and **before** the first write, append one line to `sessions/running-log.md` (create the file if it doesn't exist):

```
{DATE TIME} | {SESSION_ID} | {ENV} | {TICKET_KEY} | apply | {brief description}
```

This is the single source of truth required by `.claude/rules/firebase-safety.md`. If `apply-fix` aborts before reaching Step 4d (e.g. user rejects a write), this line still records that a session was created — `summarize-firebase-session` and rollback tooling depend on it.

**Skip on dry-run** — corrupting the log with fabricated session ids would block future rollback. Step 4f's report flags the skipped log entries.

### 4b.0. Resolve Template Artifacts (once per run, both modes)

Run **once**, immediately after 4a.5, **before** the per-write loop. Skip entirely if the deploy file has no `## Template Artifacts` section.

**Procedure:** [template-artifact-resolution.md](./references/template-artifact-resolution.md) — parses the plan's full-sha256 block, hash-verifies local twig/css files, prompts on drift (3-option a/b/c), validates `<ARTIFACT T_id ...>` placeholder references, and builds the in-memory `artifact_map` consumed by Step 4b.iii.

**Critical invariants** (the reference enforces, but callers must know):
- Every STOP path in this sub-step (malformed full-sha256 block, missing local file, drift-prompt option `b` or `c`, undefined T_id, `(unchanged)` reference) closes the empty session via `complete_session` and appends a `Run N — aborted at Step 4b.0` entry to `session-log.md` (REAL mode only).
- Drift is **never** silently accepted — always prompted via the 3-option menu.
- The local file is the source of truth for the write; the plan's sha256 is the integrity check, not the content.

**Output:** `artifact_map` keyed by `T_id` (with `{twig|css}_content`, `{twig|css}_drifted`, `local_sha256` when drifted) and `drift_summary` (used by Step 4i).

---

### 4b. For each write in deploy.md:

**Step 4b.i — Pre-write read (always, both modes):**

Read the path on `{ENV}` and capture the value as the `Before:` snapshot for Step 4f's report and the rollback plan. Use `query_rtdb` for RTDB paths, `query_firestore` for Firestore. Reads are safe in any mode.

**Create-on-absent special case** (template artifacts or otherwise): if the deploy plan's `Before:` block reads exactly `path does not exist on UAT — fresh create` (or the env-appropriate variant) AND the fresh read returns null / empty / not-found, that's a confirmed match — record `Before: confirmed absent` for Step 4f and proceed.

If the plan asserted absence but the fresh read returns data, that's drift — handle in **two structured prompts**, never one combined:

**Prompt 1 — drift acknowledgement:**

```
Plan asserts {path} does not exist on {ENV}, but it does now.

Current state on {ENV}:
[paste the fresh read result, truncated to <8 KB; template fields shown as sha256 + size descriptors per Format B conventions]

Continue with this deploy step despite the drift? (yes / no / abort)
```

- `no` → stop the write step; mark as `⚠️ skipped` in Step 4f; continue to the next write.
- `abort` → exit the per-write loop. Complete the session (per the 4b.ii abort pattern); record the abort in session-log.md.
- `yes` → record the drift event under Step 4f Notes (`Plan asserts {path} absent, found data on {ENV}; user acknowledged at <timestamp>`) AND proceed to Prompt 2.

**Prompt 2 — operation-type confirmation (only fires after Prompt 1 yes):**

The plan declared `create` semantics. Because the path already holds data, executing the plan as-is means overwriting that data. The user must explicitly approve the operation change before 4b.iii's normal preview runs:

```
Operation-type change required:
  Plan declares:   create at {path}
  Effective op:    update_full (overwriting existing data with the plan's data block)

Proceeding will REPLACE the current state shown above with the plan's data block.
Confirm operation change? (yes / no)
```

- `no` → stop the write step; mark as `⚠️ skipped` in Step 4f; continue to the next write. The user can re-run /prepare-uat with corrected semantics if they meant to update rather than create.
- `yes` → the wire call uses `operation: update_full` instead of the plan's `create`. The freshly-read existing data becomes the rollback `Before:` snapshot (replacing the plan's `path does not exist on UAT` sentinel). Step 4f's Execution Trace MUST record both the plan's declared op and the executed op (`Declared: create | Executed: update_full (operation flip on drift)`).

Splitting the prompt is mandatory — never combine drift acknowledgement and operation-type change into one `yes`. The user is making two different decisions: "is the unexpected data OK?" and "is replacing it OK?" Each gets its own surface.

**Step 4b.ii — Drift check on fields this write changes:**

Two formats are possible in the plan's `Before:` block depending on the field type. Handle both:

**Format A — Verbatim field values** (the default for non-template fields):

Compare the just-read value against the deploy plan's `Before:` snapshot, but ONLY on the fields the write step's `data` block touches (or the explicit target field for `update_partial`). Ignore housekeeping fields the plan doesn't change (`updatedAt`, `updatedBy`, etc.).

- Match → continue.
- Differ → surface a diff (`field X: plan Before = a, current {ENV} = b`) and ask `Plan's Before snapshot is stale on this step — current {ENV} value differs on a field this write would change. Continue? (yes / no / abort)`. On `yes`, replace the in-memory `Before:` snapshot with the freshly-read value for Step 4f's report and rollback. On `abort`, stop and complete-session on whatever was already written (REAL mode).

**Format B — Integrity record (sha256 + excerpt + size)** for template-artifact writes — when the `Before:` block contains lines like `Before-template-sha256: <64-char hex>`:

The plan's recorded value for the field is a hash, not the raw string. Don't try to byte-compare the 45 KB read result to the hash line. Instead:

1. For each field whose `Before:` block has a `Before-{field}-sha256:` line (and the line value is NOT `(unchanged)` or `(n/a — new path)`):
   - Hash the freshly-read field value via `shasum -a 256` over the exact bytes.
   - Compare the full 64-char hex to `Before-{field}-sha256`.
2. Outcome:
   - Match → continue.
   - Differ → surface a diff (`{field}: plan Before sha256 = {first 16}…{last 16}, current {ENV} sha256 = {first 16}…{last 16}, current size = {N KB}, plan size = {N KB}`) and ask the same yes/no/abort prompt as Format A. On `yes`, replace the in-memory `Before:` snapshot's sha256 with the freshly-computed hash and add a note under Step 4f's Notes section that the plan's recorded Before drifted from {ENV}.
3. The verbatim sibling-field block in the plan's `Before:` (a sub-section labeled `# Sibling fields (verbatim):`, present on update writes) is honored as ground truth for Step 4b.iv's post-write check — capture it now for use after the write succeeds.

Apply Format A and Format B independently per field. A single `Before:` block can contain both — for example, an `update_partial` that touches `template` (Format B: hash) while declaring sibling `label`, `kind`, `active` (Format A: verbatim).

**Step 4b.iii — Substitute placeholders, show proposed write, and ask:**

**Substitution step (only when the `data: {}` block contains `<ARTIFACT T_id {twig|css}>` placeholders):**

Replace each placeholder with the bytes stored in the artifact map (built in 4b.0.iv). The substitution is on the **wire-bound payload** the write call will receive — NOT on the deploy file (the deploy file is never modified). After substitution:

- `template: <ARTIFACT T2 twig>` → `template: "<45 KB twig string bytes>"` in the actual write call's `data` field.
- The placeholder string `<ARTIFACT T_id ...>` must NEVER reach the `write_rtdb` / `write_firestore` invocation. If you find yourself about to send the literal placeholder to a write tool, Step 4b.0 didn't run — go back and run it.

**User-facing preview (do NOT show 45 KB of inline twig in the terminal — it will be unreadable and the user can't meaningfully diff it):**

```
Write {N}/{TOTAL}: {operation} at {path}
Environment: {ENV}
Mode: {REAL | DRY-RUN}

Current state (just-read):
[result of query_rtdb / query_firestore for this path — for template fields, show `sha256 = {first 16}…{last 16}, size = {N KB}` instead of pasting the full string]

Proposed change:
[the data from deploy.md, with each <ARTIFACT T_id {twig|css}> placeholder replaced in the preview by a synthetic descriptor line:]
  template: <ARTIFACT T2 twig — 45 KB, sha256 b5d29ad0…ba98 (verified vs plan: {match | DRIFT-accepted}), source: document-templates/Cremation Booking Form/Cremation Booking Form.twig>
  styles:  <ARTIFACT T1 css  — 3 KB,  sha256 8e44d10f…3456 (verified vs plan: match), source: document-templates/Memorial Slideshow Cover/Memorial Slideshow Cover.css>
[Non-template fields render verbatim as usual: label: "Memorial Slideshow Cover", active: true, etc.]

Approve this write? (yes / no / skip)
```

The synthetic descriptor is the only visible representation of the template content — the actual bytes are still substituted into the wire call. The descriptor must always carry: T_id, file type, size, full-sha256 prefix+suffix, verification verdict (match vs DRIFT-accepted), and the local source path. If any of those is missing, Step 4b.0 didn't complete properly — re-run it.

Wait for response:
- **yes** → REAL mode: execute `write_rtdb` / `write_firestore` with the SUBSTITUTED data block (real bytes in the `template` / `styles` fields), the session_id, and `allow_writes: true`. DRY-RUN: log the call as `(SIMULATED)` for Step 4f; do not call the write tool. For Step 4f's Execution Trace, record the substituted-payload sizes (e.g. `template: <T2 twig substituted, 46080 B>`) — do NOT paste the raw 45 KB content into the deploy-result.md.
- **no** → stop. REAL mode: do NOT call `complete_session`; inform the user writes are uncommitted (the running-log line already records the abort). DRY-RUN: just exit.
- **skip** → skip this write, continue to the next. Mark as `⚠️ skipped` in Step 4f.

**Step 4b.iv — Sibling-fields integrity check (REAL only, after each successful write):**

For document-level writes, read the parent path with `shallow: true` and confirm sibling fields retained their pre-write values (apart from `updatedAt` / `updatedBy` housekeeping). Capture per-field outcome for Step 4f's report. On dry-run this is simulated — no read needed — and the report marks the check `🔵 Simulated`.

**When the plan's `Before:` block declared explicit sibling fields** (the `# Sibling fields (verbatim):` sub-section captured in Step 4b.ii Format B):

The plan's verbatim values are the authoritative invariant — not just the pre-write read snapshot. Cross-check the post-write read against BOTH:

1. The pre-write read snapshot from 4b.i (catches the write clobbering siblings during this run).
2. The plan's verbatim sibling block from 4b.ii (catches the case where the pre-write read was already wrong/stale and the write happened to preserve the wrong values).

If either comparison surfaces a discrepancy, surface it in 4f's report and ask the user `Sibling field {X} no longer matches the {pre-write read | deploy plan}. Continue running the remaining writes? (yes / no)`. The session is not failed automatically — sibling drift on a `template`-only update is a smell, not necessarily a corruption — but the user must explicitly accept before more writes go in.

### 4c. Complete Session — REAL only

Only after ALL writes are approved and executed:
```
complete_session(session_id: "{SESSION_ID}")
```

**Skip on dry-run.**

### 4d. Write Session Log — REAL only

After completing the session, append a run entry to `tickets/{TICKET_KEY}/session-log.md` (create it if it doesn't exist). Use the template at `.claude/skills/_shared/templates/session-log-template.md`.

Record:
- `session_id` returned by `create_session`
- Environment (`dev` / `uat` / `prod`)
- Date and time
- Each path written and the operation used
- The "State Before Fix" — paste the value captured in Step 4b.i (or the post-drift-acceptance value from 4b.ii) for each path
- **Pre-flight verdict** — `Pre-flight: PASS`, `Pre-flight: WARN (acknowledged: R7, R8, ...)`, or `Pre-flight: SKIPPED (dispatch failure: <reason>)` — captured from Step 2's checker dispatch

This file is the primary rollback reference. Without the session_id, rollback requires reconstructing old data manually.

**Skip on dry-run** — Step 4f's report carries the equivalent record under "Execution Trace".

### 4e. Run Verification

REAL mode: Execute the verification queries from the deploy file. Report each check as ✓ or ✗ and carry the outcome into Step 4f's Verification table.

**Hash-aware expected values** — when a Verification row's `Expected:` cell contains an expression of the form `sha256 of {field} == {truncated_hash}` (4+4 chars with `…`, e.g. `a3f9…1e2f`), do NOT string-compare the raw read result to the literal expected-cell text. Instead:

1. Read the path with the verification command in the row.
2. Extract the named field's value from the response.
3. Compute `shasum -a 256` over the value's exact bytes.
4. Compare the truncated prefix (`{first 4}…{last 4}`) of the computed full hash to the recorded truncated hash. The plan deliberately truncated for readability — the full hash is the same record in the artifact map (4b.0) or, for non-artifact fields, in the deploy plan's full-sha256 block.
5. ✓ on match, ✗ on mismatch. Multiple `sha256 of X == ...; sha256 of Y == ...` clauses in one row are AND-joined — all must pass.

**Verbatim expected values** stay verbatim — only the `sha256 of ... == ...` pattern triggers hashing.

DRY-RUN mode: Do NOT re-read the verification paths — the writes never happened, so the reads would just reflect pre-write state. Step 4f's Verification table marks every row `🔵 PENDING — real run only`. If the plan is internally inconsistent (write data and verification expected value contradict), call it out under Step 4f's Notes as `⚠️ Plan inconsistency` — never encode it as a Verification verdict.

### 4f. Write deploy-result.md (both modes)

Read [deploy-result-template.md](../_shared/templates/deploy-result-template.md). Save the output to:

```
tickets/{TICKET_KEY}/deploy-result.md
```

Mode-specific rules:

| Setting | REAL run | DRY-RUN |
|---|---|---|
| Title badge | `# {TICKET_KEY}: {ENV} Deploy Result — REAL` | `# {TICKET_KEY}: {ENV} Deploy Result — DRY-RUN SIMULATION` |
| Command blocks in Execution Trace | shown as issued, with the real `session_id` and live response payload | tagged `(SIMULATED)`; `session_id` uses a `sim-{ENV}-{TICKET_KEY-lower}-{YYYYMMDD}` placeholder; response payload is fabricated to reflect what the call *would* return |
| Verification table | actual PASS/FAIL from real post-flight reads | every row tagged `🔵 PENDING — real run only`; plan inconsistencies surfaced under Notes |
| Sign-off "Real run executed" item | ticked | unticked, with the line "this document represents a dry-run only" |
| Notes section | run-specific outcome | explicit reminder that `{ENV}` is unchanged and a real run is still required |
| "Code dependency live" row | shown for `uat` / `prod`, dropped for `dev` | same |

For multi-run scenarios (a deploy was previously attempted and now retried/extended), append a new `## Run N` section instead of overwriting — keep the file as a cumulative ledger. Increment N from the last `## Run` heading. A dry-run that precedes a real run becomes Run 1 (dry-run); the subsequent real run becomes Run 2 in the same file.

### 4g. Output Guardian pass on deploy-result.md

Re-read the saved `deploy-result.md` and strip anything that violates `.claude/rules/output-guardian.md`:
- No tool names in narrative prose (`firebase-explorer`, `mcp__...`, `getConfluencePage`, etc.)
- No "Session 124 applied" / "AI investigated" / "Claude confirmed" / "queried via" phrasing
- No internal session-id leakage in headings or summary tables — keep real session ids inside fenced code blocks
- No references to local workspace files in prose — neither bare filenames (`deploy.md`, `session-log.md`, `running-log.md`, `rca.md`, `spec.md`, `rollback.md`), nor paths under `tickets/...`, `sessions/...`, `.claude/...`, nor relative links. Replace with inline prose ("the approved deploy plan", "the session log was updated for this run"). Repo code paths like `FCRM-Web/src/forms/FormController.ts:42` are fine.

The only allowed tool references are inside fenced command blocks (`query_rtdb` / `query_firestore` / `write_rtdb` / `write_firestore` / `create_session` / `complete_session` / `rollback_session`) — those are deploy syntax, not narration.

### 4h. Upload deploy-result.md to Google Drive — REAL + (uat | prod) only, opt-in per run

After Step 4g's Output Guardian pass succeeds on a REAL run targeting `uat` or `prod`, mirror the result file to a shared Google Drive folder so the team lead can review it via a separate reader skill.

**Env + mode gate (must ALL hold to issue the prompt):**

| Condition | Behavior |
|---|---|
| Mode is DRY-RUN (any env) | **Skip entirely.** No prompt, no upload — dry-run plans are local-only and would pollute the lead's queue. |
| Env is `dev` (REAL or dry-run) | **Skip entirely.** No prompt, no upload — dev applies are testbed runs and stay local. The local `deploy-result.md` is still written by Step 4f; only the Drive mirror is suppressed. |
| Env is `uat` or `prod`, mode is REAL | Issue the user prompt per the procedure below. |

The gate is a hard skip on dev / dry-run — never ask the user "upload anyway?" on those branches. The local file is always written by Step 4f; this step controls the Drive copy only.

**Procedure:** [drive-upload-deploy-result.md](./references/drive-upload-deploy-result.md) — handles cached-folder vs first-time-setup prompts, same-name collision (replace/keep-both/abort), the multi-run slicing algorithm (uploaded copy carries the latest `## Run` block + a trailer; local file stays the full ledger), and `create_file` failure surfacing.

**Config file:** `.claude/skills/_shared/config/drive.json` — this step consumes the `deploy_result_parent_folder_id` key; writes preserve other keys (notably `template_assets_parent_folder_id` used by Step 4i).

**Key invariant:** the local `deploy-result.md` is never modified by this step — slicing is applied to the upload payload only.

### 4i. Re-upload drifted template artifacts to Drive — REAL only, conditional, opt-in

Run **only when** ALL hold: Step 4b.0 detected drift AND the user chose option `(a) accept current local content` AND mode is REAL.

Skip entirely otherwise: no Template Artifacts section, no drift, or DRY-RUN.

**Procedure:** [drive-reupload-on-drift.md](./references/drive-reupload-on-drift.md) — confirms `template_assets_parent_folder_id` is configured (with first-time-setup prompt), per-drifted-file `yes/no/abort` prompt, collision handling against the templates folder, upload + capture of new Drive URL, failure surfacing.

**Config key:** `template_assets_parent_folder_id` in `.claude/skills/_shared/config/drive.json` (NOT the `deploy_result_parent_folder_id` used by Step 4h). Writes preserve both keys.

**Failure invariant:** a failure here is supplementary — the Firebase writes already succeeded in Step 4c. Record the failure under Step 4f Notes; do NOT mark the apply itself as FAIL.

---

## Step 5: Code Fix — Apply Changes

Skip Step 5 entirely if spec.md has no Code Changes section.

**Procedure:** [code-fix-flow.md](./references/code-fix-flow.md) — blast-radius summary via `search_with_context` (5.0), code-fix pre-flight via `pipeline-checker` against `./code-checker-prompt.md` (5a), per-file approval edit loop (5b), post-edit verification via `get_review_context` (5c).

**Pre-flight rubric:** `./code-checker-prompt.md` in this skill folder is the authoritative source for code-fix checks (CR1-CR8). Keep it in sync with the reference.

**Key invariant:** no git branches or commits are created by this skill — the user handles git after the edits land.

## Step 6: Note Unexpected Findings

If you discover anything unexpected during application (a path that doesn't exist, data that differs from spec, a file that has changed), write it to `tickets/{TICKET_KEY}/notes/{DATE}-apply-findings.md` before continuing. Report it to the user.

## Step 7: Summarize

After completing all writes/changes:

```
{✓ Fix applied | 🔵 Dry-run completed} for {TICKET_KEY}

Mode: {REAL | DRY-RUN}
Environment: {ENV}
Config changes: {N} Firebase writes {executed | simulated} on {ENV}
Code changes: {N} files modified
Template artifacts: {N artifacts ({M new, K updated}); X files drifted from plan, Y re-uploaded to Drive | n/a — no Template Artifacts section in deploy plan}
Verification: {N/N PASS | N/N PENDING — dry-run}
Result file: tickets/{TICKET_KEY}/deploy-result.md ({Run N appended})
Drive mirror (deploy-result): {DRIVE_WEB_URL[ — latest run only, {N} total in local ledger] | n/a — dry-run | n/a — dev (Drive mirror is uat/prod only) | skipped — user declined | upload failed: <reason>}
Drive mirror (templates): {N re-uploaded, K declined, L not configured | n/a — no drift detected | n/a — no Template Artifacts | skipped — dry-run}
Session id: {real id | n/a — dry-run}

Next steps:
- Run `/ticket-comment {TICKET_KEY}` to post what was done {(real runs only)}
- Assign to QA for testing {(real runs only)}
- {Dry-run: review deploy-result.md, then re-run without --dry-run when ready}
```

---

## Rules

1. **Never auto-approve.** Every write requires explicit "yes" from the user.
2. **Show current state before writing.** Always query the current value before proposing a change.
3. **Production writes get an extra warning.** No exceptions.
4. **If a write fails, stop.** Do NOT complete the session. Report the error.
5. **If spec and deploy.md conflict, stop** and ask the user which to follow.
6. **Never guess Firebase paths** — only write to paths explicitly in deploy.md.

## Red Flags — STOP and reconsider

If you catch yourself thinking any of these, the next action is NOT what you were about to do. Pause and re-read the relevant Rule / Step.

- "Let me batch-approve the remaining writes to save time." → Rule 1. Every write needs its own `yes`.
- "The dry-run already proved this works, I can skip pre-flight on the real run." → Step 2 + Step 4b.i. Pre-flight runs every time; real-env state may have drifted since the dry-run.
- "The Before snapshot doesn't match the live read, but it's close enough." → Step 4b.ii. Any drift requires explicit user acknowledgement; the fresh value then replaces the stale snapshot in the result file.
- "I'll infer the DB type (RTDB vs Firestore) from the path." → Rule 6 + `firebase-safety.md`. If the deploy plan doesn't state it, query both and confirm before writing.
- "The deploy file path looks slightly different but it's clearly the same fix." → Step 1c. Use ONLY the file resolved by the locator; never silently merge two deploy files.
- "Code dependency is probably live, the deploy plan looks safe." → Step 3a. Get explicit user confirmation on uat / prod before any write — never infer.
- "The first write failed; I'll retry inside the same session." → Rule 4. A failed write means STOP. Investigate, then start a NEW session if needed.
- "I'll run prod first attempt as REAL because the deploy plan was reviewed." → Step 3. Prod first attempt is dry-run; REAL prod runs require both the extra warning AND explicit `yes`.
- "Verification row V2 looks like it would pass — I'll mark it ✅." → Step 4e. Only mark PASS after the actual post-flight read returns the expected value. DRY-RUN is always `🔵 PENDING`.
- "The `<ARTIFACT T1 twig>` in the data block is obvious — apply-fix will figure it out, no need to substitute." → Step 4b.0 + 4b.iii. The literal placeholder string must be replaced with the local file's bytes before the write call. A skipped substitution writes the literal placeholder string into Firebase and silently corrupts the template.
- "The plan's `Before-template-sha256: 1111aaaa…` is the expected value; I'll string-compare it to the read." → Step 4b.ii Format B. The plan records a hash, not the value. Hash the freshly-read field and full-hex compare to the plan's sha256.
- "The local twig drifted from the plan's hash, but the diff looks like a whitespace fix — I'll accept silently." → Step 4b.0.ii. Drift is a three-option user prompt (`a / b / c`); silent acceptance is not in the menu. Even a one-byte difference must be acknowledged.
- "Verification row says `sha256 of template field == a3f9…1e2f` — I'll just look at the read result and eyeball whether it 'looks like' the new twig." → Step 4e. Read the field, hash it, compare the truncated prefix. Visual comparison of 45 KB of twig is not a verification.
- "The deploy plan has a Template Artifacts table but no full-sha256 block — close enough, I'll use the truncated hashes." → Step 4b.0.i. STOP. Truncated 4+4 hashes can collide (prefix+suffix is 16^8 = 4.3B — collisions are reachable). The full block is mandatory.
- "Step 4i Drive re-upload failed — I'll mark the whole apply as FAIL." → Step 4i failure handling. The Firebase writes already succeeded (Step 4c completed the session). The Drive mirror is supplementary; failure here gets noted, not fatal.

## Common Mistakes

| Mistake | What to do instead |
|---|---|
| Using `write_rtdb` for a Firestore path (or vice versa). | Match the DB column from the Writes table. If the plan doesn't state it, query both before writing. |
| Approving all writes at once (`yes, yes, yes, …`) to move faster. | One `yes` per write, after seeing the proposed change. |
| Running `apply-fix {KEY} prod` REAL as the first prod attempt. | Always `apply-fix {KEY} prod --dry-run` first. Only re-run REAL after reviewing the dry-run result file. |
| Including session ids, `firebase-explorer`, or `tickets/{KEY}/…` paths in `deploy-result.md` prose. | Step 4g Output Guardian pass — session ids live inside fenced command blocks only; tool refs only as deploy syntax; no workspace paths in narrative. |
| Marking the Verification matrix PASS without running the post-flight read. | Only PASS after the read returns the expected value; ❌ on mismatch; `🔵 PENDING — real run only` on dry-run. |
| Re-using a session id after a failed write to "continue from where it stopped". | Stop the session, investigate the failure, start a fresh session for the retry. |
| Skipping the sibling-fields integrity check because "I only updated one field". | Step 4b.iv runs every time — even single-field updates can clobber siblings on `update_full`. |
| Uploading to Drive while the local file has merge conflicts or stray editor markers. | Re-read after Step 4g; the slicing logic in Step 4h.iii assumes well-formed `## Run N` headings. |
| Treating a partial run (e.g. 2 of 3 writes succeeded, 1 aborted) as ✅ PASS. | Status is ⚠️ PARTIAL with a one-line reason. Verification is PASS only on the rows that actually wrote. |

## Quality Bar

- [ ] Run mode (`REAL` vs `DRY-RUN`) resolved from `$ARGUMENTS` and surfaced in the Step 3 confirmation
- [ ] Pre-flight check (Step 2) ran — verdict captured (PASS / WARN with acknowledged rule IDs / SKIPPED with reason)
- [ ] Code-dependency notice surfaced and explicitly confirmed by the user before any write (uat / prod only; skipped for dev)
- [ ] No Firebase write executed without explicit `yes` from the user
- [ ] Current state of each path queried before proposing the change (4b.i)
- [ ] Drift check (4b.ii) compared the fresh read to the plan's `Before:` snapshot on fields this write changes; any drift surfaced and explicitly accepted; freshly-read value replaced the stale `Before:` for report + rollback
- [ ] Sibling-fields integrity check (4b.iv) performed on every successful write (REAL) or simulated (DRY-RUN)
- [ ] Production writes received the extra warning AND received explicit confirmation (REAL mode only)
- [ ] On REAL: Session created for the target env, `session_id` saved before any write
- [ ] On REAL: Session completed ONLY after all approved writes succeeded — never on failure
- [ ] On REAL: State Before Fix recorded for each path in `tickets/{TICKET_KEY}/session-log.md`
- [ ] On REAL: Session log entry includes: `session_id`, env, date, every path written, the pre-flight verdict
- [ ] On REAL: Running log appended to `sessions/running-log.md`
- [ ] On DRY-RUN: `running-log.md` and `session-log.md` were **not** touched
- [ ] No Firebase paths invented — every path written (or simulated) appears in the deploy file (or `spec.md`)
- [ ] Correct DB tool per path: `write_rtdb` for RTDB paths, `write_firestore` for Firestore paths (no mixing)
- [ ] Code-fix blast radius checked with `search_with_context` before edits — summary built in Step 5.0
- [ ] Code-fix pre-flight (Step 5a) ran — verdict captured (PASS / WARN with acknowledged rule IDs / SKIPPED with reason)
- [ ] Code-fix file content read and matched against `spec.md` before edit
- [ ] No git branches or commits created — left for the user
- [ ] On REAL: Verification queries from the deploy file run after writes — each row recorded as PASS or FAIL
- [ ] On DRY-RUN: Verification rows recorded as `🔵 PENDING — real run only` (never PASS / FAIL); plan inconsistencies noted under the result file's Notes
- [ ] `tickets/{TICKET_KEY}/deploy-result.md` produced (REAL or DRY-RUN; multi-run scenarios append `## Run N`)
- [ ] Output Guardian pass clean on `deploy-result.md` — no internal tool names, no references to local workspace files (`deploy.md`, `session-log.md`, `running-log.md`, `tickets/...`, relative links)
- [ ] On REAL + env=`dev`: Drive mirror step SKIPPED entirely — no prompt, no upload, cache unchanged; Step 7 reports `Drive mirror (deploy-result): n/a — dev (Drive mirror is uat/prod only)`
- [ ] On REAL + env=`uat`/`prod` + cached folder: ONE combined prompt issued — `yes / yes:<URL> / no` — showing the cached folder URL
- [ ] On REAL + env=`uat`/`prod` + first-time setup: TWO prompts issued — opt-in `yes / no`, then folder URL/id — config saved to `drive.json`
- [ ] On REAL + env=`uat`/`prod` + answered `yes:<URL>`: new folder id parsed, validated via `get_file_metadata`, cache overwritten
- [ ] On REAL + env=`uat`/`prod` + uploading: payload SLICED to header + latest `## Run N` block (older runs excluded; single-run files uploaded as-is); local `deploy-result.md` not modified
- [ ] On REAL + env=`uat`/`prod` + uploading: `{TICKET_KEY}-deploy-result.md` uploaded via `create_file`; existing same-name files surfaced and resolved by the user (replace / keep-both / abort)
- [ ] On REAL + env=`uat`/`prod` + uploaded: Drive web URL reported in Step 7 summary; when ≥2 `## Run` blocks existed locally, summary appends `— latest run only, {N} total in local ledger`
- [ ] On REAL + env=`uat`/`prod` + user said `no`: Step 7 summary reports `Drive mirror: skipped — user declined`; no upload happened; cache unchanged
- [ ] On DRY-RUN (any env): NO Drive prompt issued; NO upload happened
- [ ] Secrets Safety honored — no secret values copied into session logs, deploy artifacts, output, or Drive upload payload

**Template-artifact items** (skip when the deploy file has no `## Template Artifacts` section):

- [ ] Step 4b.0 ran once, before any per-write step, when the deploy file had a Template Artifacts section
- [ ] Full-sha256 block parsed; STOP fired if the truncated table was present without a full block
- [ ] Every artifact's local `.twig` / `.css` file verified to exist at `document-templates/{Name}/{Name}.{twig|css}`; STOP fired on missing files (no session was created)
- [ ] Local sha256 computed via `shasum -a 256` and compared to plan's full-sha256 (64-char hex match, not truncated)
- [ ] On hash mismatch, the three-option prompt (a / b / c) was issued; the user's explicit choice was recorded; no silent acceptance of drift
- [ ] Every `<ARTIFACT T_id {twig|css}>` placeholder in any `data: {}` block was validated against the artifact map; STOP fired on undefined T_ids or `(unchanged)` references
- [ ] Step 4b.iii substitution happened on the WIRE payload — no `<ARTIFACT …>` placeholder string was ever passed to `write_rtdb` / `write_firestore`
- [ ] Step 4b.iii preview showed synthetic descriptor lines (T_id, size, sha256 prefix+suffix, verification verdict, source path) — never 45 KB of raw twig content in the terminal
- [ ] Step 4b.i recognized `path does not exist on UAT — fresh create` as a create-on-absent assertion and confirmed it against the fresh read; surface fired on assertion-vs-read mismatch
- [ ] Step 4b.ii Format B (hash-based drift check) ran for every `Before-{field}-sha256:` line; the freshly-read field was hashed and compared full-hex
- [ ] Step 4b.iv cross-checked sibling fields against BOTH pre-write snapshot AND plan's `# Sibling fields (verbatim):` block when present
- [ ] Step 4e Verification rows with `sha256 of {field} == {truncated}` were hashed-and-prefix-compared, not string-compared
- [ ] Step 4i ran only when drift was detected AND user accepted local content; never on dry-run; never when no drift occurred
- [ ] On Step 4i re-upload: `template_assets_parent_folder_id` was used (not `deploy_result_parent_folder_id`); `drive.json` writes preserved both keys
- [ ] Step 4f's deploy-result.md does NOT contain the verbatim twig/css content — only sha256 / size / source-path descriptors
- [ ] Step 7 summary covers Template artifacts (counts, drift, re-uploads) and Drive mirror (templates) verdicts
- [ ] On a Step 4b.0 STOP (malformed plan / missing local file / drift abort / undefined T_id / unchanged-reference): if a session was created in 4a, `complete_session` was called before exit and a `Run N — aborted at Step 4b.0` entry was appended to session-log.md
- [ ] On a Step 4b.i create-on-absent drift (plan asserts absent, fresh read returns data): TWO structured prompts were issued — drift acknowledgement first, operation-type confirmation second; both required explicit `yes` before any write; Step 4f Execution Trace recorded both `Declared: create` and `Executed: update_full (operation flip on drift)`

## Next step

After completing this skill, select EXACTLY ONE action from the decision tree below based on the env you just applied to. Print the block below with the chosen action substituted for `{ACTION_LINE}`. Substitute the actual ticket key for `{TICKET_KEY}`. Do NOT print the decision tree.

**Decision tree (reasoning input only):**

| Env just applied to | `{ACTION_LINE}` |
|---|---|
| `dev` | `/ticket-comment {TICKET_KEY}, then /apply-fix {TICKET_KEY} uat to promote` |
| `uat` | `/ticket-comment {TICKET_KEY}, then /apply-fix {TICKET_KEY} prod to promote` |
| `prod` | `/ticket-comment {TICKET_KEY}, then /publish-rca {TICKET_KEY} to finalize` |

**Block to print:**

```
---
**Next step**

{ACTION_LINE}
---
```
