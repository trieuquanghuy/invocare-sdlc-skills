---
name: task-status
description: "Use when checking the current status of a ticket at the start of the day or after time away. Triggers on: check status, what's the status, where are we on GEN-XXXX, daily check, morning check, task update, what's done, what's next, check progress, standup, overview all tickets."
argument-hint: "Jira ticket key (e.g. GEN-2759) — omit for overview of all active tickets"
---

# Task Status

**Read-only daily check.** Pulls fresh Jira and Confluence data, compares against local artifacts, and shows: what's new, what's been done, where the fix is across environments, and what to do next. Does not execute anything.

**Output guardian:** all output reads as written by a developer. Never mention tool names, session IDs, MCP calls, or any indication of automation.

**Git safety:** apply `.claude/rules/git-safety.md` — read-only operations only (this skill never writes); refuse on dangerous git states for the config-drift check.

## NOT This Skill If

- User wants to apply a fix to any environment (dev / uat / prod) → use `/apply-fix {TICKET_KEY} {env}`.
- User wants to draft a UAT deploy file from a Confluence handoff comment → use `/prepare-uat {TICKET_KEY}` first, then `/apply-fix {TICKET_KEY} uat`.
- User wants to publish the RCA to Confluence → use `/publish-rca`.
- User wants to post a Jira comment summarising what was done → use `/ticket-comment`.
- User wants a summary of every Firebase session in this Claude session (cross-ticket) → use `/summarize-firebase-session`.

---

## Modes

| Invocation | Behaviour |
|------------|-----------|
| `/task-status` | Overview table of ALL tickets, then detail for the most recently modified one |
| `/task-status GEN-XXXX` | Full detail for a specific ticket |
| `/task-status --all` | Full status card for every active ticket in sequence |
| `/task-status --standup` | Standup-only blurbs for all active tickets, no detail cards |

---

## Step 0: Identify Mode and Tickets

**With a ticket key:** go directly to Step 2.

**With no argument:**
1. Scan `tickets/` for all subdirectories
2. Note last-modified timestamp and artifact files per folder
3. Run Step 1 (overview table)
4. Run full detail flow for the most recently modified ticket
5. Ask: "Want detail on another ticket?"

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

## Step 2: Read Local Artifacts

Read everything in `tickets/{TICKET_KEY}/`:

| File | What it tells you |
|------|-------------------|
| `rca.md` | Root cause, currency classification, Confluence URL |
| `spec.md` | Fix type (config / code / mixed), repos/files |
| `deploy.md` | Firebase write steps |
| `session-log.md` | Every run: action, env, date, paths written |
| `validation.md` | UAT test scenarios |
| `rollback.md` | Rollback plan exists |
| `.last-checked` | Timestamp of last `/task-status` — baseline for "new since" |
| Any `{TICKET_KEY}-deploy-uat.md` | UAT deploy plan authored by `/prepare-uat` — presence means UAT migration prep is done |
| `notes/*-apply-findings.md` | Unexpected findings from an `apply-fix` run — see Step 2b |

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

## Step 3: Fetch Fresh Jira Data

```
getJiraIssue(cloudId: "invocarecompass.atlassian.net", issueIdOrKey: "{TICKET_KEY}")
```

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

## Step 4: Check Confluence

Use Confluence URL from `rca.md` if present. Otherwise:
```
searchConfluenceUsingCql(cql: 'title ~ "{TICKET_KEY}" AND type = page')
```

If found: check for comments newer than baseline, classify same as Jira.
If not found: note "RCA not yet published to Confluence".

---

## Step 5: Config Drift Check (config / mixed fixes with session-log only)

Skip if: code-only fix, or no apply runs in session-log.

**Read-only, dev-only** (per `firebase-safety.md`): this check only *reads* the dev environment — never `query` other envs and never any write tool. State the DB per path (RTDB vs Firestore) and use the matching read tool; the rows below assume RTDB, so use `query_firestore` instead when `session-log.md` records the path as a Firestore write.

For each path in the most recent dev apply, re-query dev with the read tool for that path's DB:
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

```bash
# BASE resolves to $INVOCARE_ROOT if set, otherwise the current working directory.
# Run /task-status from the project root, or set INVOCARE_ROOT in your shell.
BASE="${INVOCARE_ROOT:-$(pwd)}"
REPOS="FCRM-Web FCRM-Cloud-Functions FCRM-Cloud-App FCRM-Exports-API FCRM-Reports-API \
       FCRM-Email-API FCRM-Files-API Barndoor-Auth-App Barndoor-Batch-App"
found=0
total=0
for repo in $REPOS; do
  total=$((total+1))
  if [ -d "$BASE/$repo/.git" ]; then
    found=$((found+1))
    git -C "$BASE/$repo" log --all --oneline --grep="{TICKET_KEY}" \
      | sed "s/^/$repo: /"
  else
    echo "$repo: (not present locally — skipping)"
  fi
done
if [ "$found" -eq 0 ]; then
  echo ""
  echo "⚠️  0 of $total repos resolved under \$BASE=$BASE"
  echo "    Set INVOCARE_ROOT to your project root, or run /task-status from inside it."
fi
```

Per repo:
- Commit found → `{REPO}: {HASH} {MESSAGE} ({DATE} on {BRANCH})`
- No matching commit → omit the repo from output (git produces no rows)
- Repo not cloned locally → `{REPO}: (not present locally — skipping)` so coverage gaps are visible

If no rows from any repo: "No commits found for {TICKET_KEY}".

---

## Step 7: UAT Checklist (if validation.md exists)

Extract each test scenario. Cross-reference against new Jira comments:
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
    Resolve before promoting: read `tickets/{TICKET_KEY}/notes/{filename}` then acknowledge in session-log.md

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

After output, write current timestamp to `tickets/{TICKET_KEY}/.last-checked`.

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
- [ ] `.last-checked` written after output
- [ ] No tool names, session IDs, or automation language in any output

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
