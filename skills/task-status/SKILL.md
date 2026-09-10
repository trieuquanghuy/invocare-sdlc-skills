---
name: task-status
description: "Use when checking the current status of a ticket at the start of the day or after time away. Triggers on: check status, what's the status, where are we on GEN-XXXX, daily check, morning check, task update, what's done, what's next, check progress, standup, overview all tickets."
argument-hint: "Jira ticket key (e.g. GEN-2759) — omit for overview of all active tickets"
---

# Task Status

**Read-mostly daily check with a local cache write.** Pulls fresh Jira and Confluence data, compares against local artifacts, and shows: what's new, what's been done, where the fix is across environments, and what to do next. It writes only the ticket-scoped `.last-checked` cache described in Step 9.

**Output guardian:** all output reads as written by a developer. Never mention tool names, session IDs, MCP calls, or any indication of automation.

**Git safety:** apply `.claude/rules/git-safety.md` — Git and external systems remain read-only; the only write is the ticket-scoped local cache. Refuse on dangerous git states for the config-drift check.

## NOT This Skill If

- User wants to apply a fix to any environment (dev / uat / prod) → use `/apply-fix {TICKET_KEY} {env}`.
- User wants to draft a UAT deploy file from a Confluence handoff comment → use `/prepare-uat {TICKET_KEY}` first, then `/apply-fix {TICKET_KEY} uat`.
- User wants to publish the RCA to Confluence → use `/publish-rca`.
- User wants to post a Jira comment summarising what was done → use `/ticket-comment`.

---

## Modes

| Invocation | Behaviour |
|------------|-----------|
| `/task-status` | Overview table of ALL tickets, then detail for the most recently modified one |
| `/task-status GEN-XXXX` | Full detail for a specific ticket |
| `/task-status --all` | Full status card for every active ticket in sequence |
| `/task-status --standup` | Standup-only blurbs for all active tickets, no detail cards |

---

## Execution plan: two parallel batches, then write

The steps below are numbered for reading order, not execution order. Run them as two batches of parallel tool calls — nothing in batch 1 depends on anything else in batch 1:

- **Batch 1 (one turn, two parallel calls):** `bash .claude/skills/task-status/scripts/extract.sh {TICKET_KEY}` (covers Steps 2 AND 6 — all local facts plus the git scan) + Step 3 Jira fetch.
- **Batch 2 (one turn):** Step 4 Confluence (needs the URL from batch 1) + Step 5 config drift queries in parallel (paths come from the LATEST RUN SECTION of the script output). Skip whichever the skip rules eliminate.
- Then build the card (Step 8) and write `.last-checked` (Step 9).

Total: ~4–6 tool calls. Do not hand-write extraction greps — the script already emits every field Steps 2/6 need.

## Step 0: Identify Mode and Tickets

**With a ticket key:** go directly to Step 2.

**With no argument:**
1. One shell pass over `tickets/` — never Read files per folder for the overview:
   ```bash
   for d in tickets/*/; do
     echo "== $d $(ls "$d" | tr '\n' ' ')"
     grep -E '^\- \*\*(Environment|Action|Date)' "$d/session-log.md" 2>/dev/null | tail -6
   done
   ```
   File presence gives the stage; the session-log tail gives env progress and last activity.
2. Run Step 1 (overview table)
3. Run full detail flow for the most recently modified ticket
4. Ask: "Want detail on another ticket?"

---

## Step 1: Overview Table (multi-ticket mode only)

Determine stage and env progress from local files only — no Jira calls yet.

**Pipeline stage** — first match wins:

| Condition | Stage label |
|-----------|-------------|
| No meaningful files | Not started |
| `rca.md` only | Investigated |
| `rca.md` + `spec.md`, no session-log | Spec ready |
| session-log has dev apply, no UAT apply | Fix applied — DEV |
| session-log has UAT apply, no prod apply | Fix applied — UAT |
| session-log has prod apply | Fix applied — PROD |
| Jira status = Done | Complete |

**Environment progress** from `session-log.md` — track latest action per env. Reverted env = ↩️.

**Sort order:** blocked tickets first → priority (Critical > High > Medium > Low) → last activity descending.

```
# Ticket Overview — {TODAY_DATE}

| Ticket   | Priority | Stage              | Environments             | Last activity |
|----------|----------|--------------------|--------------------------|---------------|
| GEN-2759 | High     | Fix applied — DEV  | DEV ✅  UAT ⬜  PROD ⬜ | 2026-04-22    |
| GEN-2757 | Medium   | Spec ready         | —                        | 2026-04-21    |
| GEN-1662 | Low      | Complete           | DEV ✅  UAT ✅  PROD ⬜ | 2026-03-15    |
| FIR-1952 | High     | Investigated       | —                        | 2026-04-18    |

Showing detail for GEN-2759. Ask for another ticket if needed.
```

---

## Step 2: Extract From Local Artifacts (targeted — never read large files in full)

A status check needs ~15 facts, but a mature ticket carries thousands of lines. Run the bundled extractor — it emits every fact this step and Step 6 need, clearly sectioned:

```bash
bash .claude/skills/task-status/scripts/extract.sh {TICKET_KEY}
```

Sections it returns: FILES (artifact presence = stage signal, incl. `{TICKET_KEY}-deploy-uat.md`), SESSION-LOG RUNS (env/date/action per run — latest per env wins), LATEST RUN SECTION (drift-check paths for Step 5), RCA (currency + Confluence URL), SPEC (fix type + repos), VALIDATION SCENARIOS (Step 7 titles), NOTES first-3-lines (Step 2b), LAST-CHECKED (baseline), GIT COMMITS (Step 6).

Never Read a large artifact (>~150 lines) in full; if a script section is ambiguous AND the ambiguity changes the status card, run one narrow follow-up grep — not a full Read.

**Baseline date for "new since last check":**
- `.last-checked` → use its timestamp
- else session-log → most recent run date
- else rca.md → its last-modified date
- else → show all activity

**From `session-log.md`:** group runs by env. Note latest apply date and whether rollback is available (apply run present = yes) per env.

**From `rca.md`:** currency (`CURRENT` / `PARTIALLY_STALE` / `OUTDATED`) and Confluence URL if present.

**From `spec.md`:** fix type, repos and files for code changes.

### Step 2b: Apply-findings notes

For each file in `tickets/{TICKET_KEY}/notes/*-apply-findings.md`, read the first 3 lines and the date in the filename. An entry is **unread** if the most recent `session-log.md` run does NOT contain a `**Notes acknowledged:** [filename]` line referencing it.

Capture for the status card:

```
⚠️  Apply findings from {DATE} ({ENV}): {first-line summary} — UNREAD
```

If notes exist but have all been acknowledged in session-log.md, omit from the status card (they're resolved).

---

## Step 3: Fetch Fresh Jira Data (fields-scoped — the Jira payload is this skill's biggest cost)

A bare `getJiraIssue` returns the full description, every comment ever written, and rendered bodies — on a long-lived ticket that's tens of thousands of tokens, most of it older than the baseline and therefore already processed on a previous check. Scope the request:

```
getJiraIssue(cloudId: "invocarecompass.atlassian.net", issueIdOrKey: "{TICKET_KEY}",
             fields: ["summary","status","assignee","priority","labels","updated",
                      "issuelinks","comment","customfield_10020"])   // 10020 = sprint
```

Comment discipline: the response returns comments oldest-first — **process only those with `created`/`updated` newer than the baseline**; skim newest-first and stop at the first comment older than baseline. Never summarize, classify, or re-read pre-baseline comments — they were handled on the run that set the baseline. Do not request or read the ticket description at all: the status card never uses it (local rca.md already owns the problem statement).

Extract:
- Status, assignee, last updated, **priority**, **labels**, **sprint name + end date**
- **Issue links** — all types:

| Link type | Display |
|-----------|---------|
| `is blocked by` | ⛔ BLOCKED BY {KEY}: {summary} |
| `blocks` | ⚠️ Blocks {KEY}: {summary} |
| `relates to` | → Related: {KEY} |
| `is subtask of` / parent | ↑ Epic/Parent: {KEY} |
| subtasks | ↓ Subtask: {KEY} |

- **Comments** newer than baseline — classify each:
  - UAT confirmation: "confirmed", "verified", "pass", "approved"
  - UAT rejection: "failed", "blocked", "not working", "wrong"
  - Scope change: new requirements or changed criteria
  - Handoff: "ready for QA", reassigned

**Staleness warnings — flag if:**
- Same Jira status > 5 days → ⚠️ `{N} days in {STATUS}`
- `spec.md` exists, no session-log, spec > 3 days old → ⚠️ `Spec ready {N} days — applied manually?`
- `rca.md` OUTDATED / unclassified and > 7 days old → ⚠️ `RCA may be stale`
- Dev fix > 5 days old, UAT still pending → ⚠️ `Dev fix {N} days old — UAT not started`

**Sprint deadline warning** — sprint ends within 2 days and ticket not Done:
> ⏰ Sprint ends {DATE} ({N} days) — ticket not yet complete

---

## Step 4: Check Confluence (skip when the answer is already known)

- URL in `rca.md` (or cached in `.last-checked`) → fetch that page's comments newer than baseline, classify same as Jira. No search.
- No URL AND no dev apply yet → the RCA is simply not published yet; note "RCA not yet published to Confluence" and **do not search** — an unpublished early-stage ticket returns nothing, every time.
- No URL but fix already applied somewhere → one CQL search: `searchConfluenceUsingCql(cql: 'title ~ "{TICKET_KEY}" AND type = page')`. Cache the outcome (URL or `none`) in `.last-checked` (Step 9) so future runs never repeat the search.

---

## Step 5: Config Drift Check (config / mixed fixes with session-log only)

Skip if: code-only fix, or no apply runs in session-log.

**Read-only, dev-only** (per `firebase-safety.md`): this check only *reads* the dev environment — never `query` other envs and never any write tool. State the DB per path (RTDB vs Firestore) and use the matching read tool; the rows below assume RTDB, so use `query_firestore` instead when `session-log.md` records the path as a Firestore write.

Spot-check, don't audit: re-query **at most 4 signature paths** from the most recent dev apply (pick the ones whose values define the fix — a full re-verification belongs to `/apply-fix`, not a daily status check). Issue the queries **in parallel in one turn**, using the read tool for each path's DB:
```
query_rtdb(path: "{PATH}", environment: "dev")
```

| Result | Display |
|--------|---------|
| Matches expected | ✅ Config at `{PATH}` intact |
| Differs | ⚠️ Config drift at `{PATH}` — expected `{X}`, got `{Y}` |
| Not found | ⚠️ Path `{PATH}` missing — fix may have been removed |

---

## Step 6: Check Git Commits (code / mixed fixes only)

Already covered: the GIT COMMITS section of the Step 2 `extract.sh` output scans all nine repos (`FCRM-*`, `Barndoor-*`) — do not run a separate git pass.

Per repo:
- Commit found → `{REPO}: {HASH} {MESSAGE} ({DATE} on {BRANCH})`
- No matching commit → omit the repo from output (git produces no rows)
- Repo not cloned locally → `{REPO}: (not present locally — skipping)` so coverage gaps are visible

If no rows from any repo: "No commits found for {TICKET_KEY}".

---

## Step 7: UAT Checklist (if validation.md exists)

Use the VALIDATION SCENARIOS section of the `extract.sh` output (titles only; never read validation.md in full). Cross-reference against new Jira comments:
- Comment confirms scenario → ✅
- Otherwise → ⬜

---

## Step 8: Build the Status Card

```
# Task Status: {TICKET_KEY} — {TODAY_DATE}

**{TICKET_TITLE}**
Priority: {PRIORITY} | Jira: {STATUS} | Sprint: {SPRINT_NAME} (ends {DATE})
Assigned: {ASSIGNEE} | Last updated: {TIME_AGO}
{Labels: {labels} — only if present}

{IF Confluence URL:}
📄 Confluence RCA: {URL}

{IF sprint deadline warning:}
⏰ Sprint ends {DATE} ({N} days) — not yet complete

{IF issue links:}
⛔ BLOCKED BY {KEY}: {summary}
⚠️  Blocks {KEY}: {summary}
↑  Epic: {KEY}: {summary}

---

## Environment Progress

DEV {✅|↩️|⬜}  →  UAT {✅|↩️|⬜}  →  PROD {✅|↩️|⬜}

| Env  | Last action | Date       | Fix age  | Rollback available |
|------|-------------|------------|----------|--------------------|
| dev  | applied     | 2026-04-22 | 1 day    | Yes                |
| uat  | —           | —          | —        | —                  |
| prod | —           | —          | —        | —                  |

{IF config drift:}
⚠️  Config drift on dev — verify before migrating to UAT

---

## New Since Last Check
Baseline: {BASELINE_DATE}

{IF new activity:}
- [{DATE}] {AUTHOR} (Jira): "{SUMMARY}" — {CLASSIFICATION}
- [{DATE}] {AUTHOR} (Confluence): "{SUMMARY}"
{IF none:}
- No new activity since last check

{IF staleness warnings:}
⚠️  {warning}

{IF unread apply-findings:}
⚠️  Apply findings from {DATE} ({ENV}): {summary} — UNREAD
    Resolve the unread finding before promotion, then record the acknowledgement.

---

## Fix Progress

Pipeline: {STAGE}

DONE:
✅ RCA created ({currency})
✅ Spec generated
✅ Fix applied to dev ({DATE})
✅ Fix applied to UAT ({DATE})
✅ Confluence RCA published

NEXT:
⬜ {remaining step}
⬜ {remaining step}

---

## What Was Changed
{Only if fix applied to at least one env}

Config (RTDB):
- `{PATH}`: {plain English description of change}

Code:
- {REPO}: {hash} {message} ({branch})

---

## UAT Checklist
{Only if validation.md exists}

✅ {confirmed scenario}
⬜ {pending scenario}

---

## Standup Blurb

{Monday → "Yesterday (Friday):"; otherwise "Yesterday:"}

Yesterday{( Friday) if Monday}: {last meaningful action — one line, no tool names}
Today: {single concrete next step}
Blockers: {BLOCKER_KEY: reason | None}
```

---

## Step 9: Write `.last-checked`

After output, write to `tickets/{TICKET_KEY}/.last-checked` a small JSON cache:

```json
{"ts": "2026-08-22T09:15:00+07:00", "confluence": "{URL or none}"}
```

`ts` is the "new since" baseline; `confluence` lets Step 4 skip the CQL search forever after. A legacy file containing only a bare timestamp is still a valid baseline — read it as `ts`, upgrade the format on this write.

---

## Next Action

One sentence. The single most logical next step based on current state:

| Situation | Suggest |
|-----------|---------|
| Not started | `/create-rca {TICKET_KEY}` |
| RCA done, no spec | `/create-spec {TICKET_KEY}` |
| Spec ready, not applied | `/apply-fix {TICKET_KEY} dev` |
| Spec waiting > 3 days | "Was this applied manually? If not, run `/apply-fix {TICKET_KEY} dev`" |
| Config drift on dev | "Resolve drift before promoting to UAT" |
| Dev fix done, no `{TICKET_KEY}-deploy-uat.md` yet | `/prepare-uat {TICKET_KEY}` |
| Dev fix done, `{TICKET_KEY}-deploy-uat.md` present | `/apply-fix {TICKET_KEY} uat` |
| QA/UAT rejected the fix (round failed) | `/apply-fix {TICKET_KEY} dev` — next fix round after triaging the failures |
| UAT done, no Jira comment | `/ticket-comment {TICKET_KEY}` |
| UAT done, need prod | `/apply-fix {TICKET_KEY} prod` |
| Done on all envs, RCA not published to Confluence | `/publish-rca {TICKET_KEY}` |
| Blocked | "Resolve {BLOCKER_KEY} first" |
| RCA outdated | `/create-rca {TICKET_KEY}` to refresh |
| Jira = Done | "Ticket closed — archive folder if done" |

> "Next: `{command}` — {one-line reason}"

This table is the **single source of truth** for next-action routing — the `## Next step` section below reuses it rather than maintaining a parallel list.

---

## Quality Bar

- [ ] Jira fetched fresh — status, priority, sprint, links, new comments
- [ ] Sprint deadline warning if ≤ 2 days
- [ ] All issue link types captured
- [ ] Baseline date correct: `.last-checked` → session-log → rca.md → all-time
- [ ] Session-log parsed per run: action, env, date — rollback availability noted
- [ ] Config drift checked for dev apply paths (config/mixed only)
- [ ] Git commits searched (code/mixed only)
- [ ] UAT checklist from validation.md crossed against new comments
- [ ] Staleness warnings emitted
- [ ] Standup blurb is 3 lines, Monday-aware, copy-paste ready
- [ ] Confluence URL surfaced
- [ ] Single next action stated clearly
- [ ] Unread apply-findings notes surfaced as ⚠️ if any exist (Step 2b)
- [ ] `.last-checked` written after output (JSON: ts + confluence)
- [ ] No tool names, session IDs, or automation language in any output
- [ ] No large artifact (>~150 lines) was Read in full — targeted extraction only (Step 2)
- [ ] Confluence CQL search ran at most once per ticket lifetime (Step 4 skip rules honored)
- [ ] Jira fetched fields-scoped; no pre-baseline comment was processed (Step 3)
- [ ] Config drift capped at ≤4 signature paths, queried in parallel (Step 5)
- [ ] Steps ran as the two parallel batches (~4–6 tool calls total); extract.sh used, no hand-written extraction greps

## Next step

After completing this skill, pick EXACTLY ONE action using the canonical **Next Action** table above (the `## Next Action` section is the single source of truth for routing — don't restate it here). Match the row whose situation describes what the status check revealed; if none of the actionable rows match, the ticket is complete or blocked, so use `nothing to do — see the status card above for context`. Then print the block below with that single action substituted in. Do NOT print the table itself — it's your reasoning input, not output.

Substitute the chosen action for `{ACTION_LINE}` in the block below. Substitute the actual ticket key for `{TICKET_KEY}`.

**Block to print** (with the single chosen action filled in):

```
---
**Next step**

{ACTION_LINE}
---
```

Example: if the status check showed `rca.md` exists but no `spec.md`, the printed block is:

```
---
**Next step**

/create-spec GEN-1945
---
```
