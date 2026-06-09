---
name: create-release-report
description: "Use when assembling a release note / release report and publishing it to Confluence after review. Combines two ticket classes: (1) migration tickets discovered automatically under /tickets — status read from deploy.md / session-log.md / deploy-result.md; (2) code-only tickets supplied by the user — status read from Jira plus linked PR(s). Drafts release-report-{DATE}.md locally for review, then publishes to Confluence on confirmation. Triggers on: release report, release note, release summary, publish release, draft release."
argument-hint: "Release date as DD MMM YYYY (e.g. 12 May 2026)"
disable-model-invocation: true
---

# Create Release Report and Publish to Confluence

Assemble a release report from the local `/tickets` folder and publish it to Confluence after user review.

**Output guardian:** all output reads as written by a developer. Apply `.claude/rules/output-guardian.md` and `.claude/rules/secrets-safety.md` — never include tool names, session IDs, local artifact paths, or any indication of automation in the report body, the Confluence page, or any user-facing summary.

**Firebase safety:** this skill is read-only. It does NOT call any Firebase write tool. Apply `.claude/rules/firebase-safety.md`.

---

## What this skill produces

1. A local draft at `release-report-{YYYY-MM-DD}.md` in the repo root, following the existing release-report draft conventions (Executive Summary, Tickets by Outcome, Data Migration Scripts, Appendix: Methodology).
2. After user review, a Confluence page under the user-specified parent in space **KMS2**.

## Ticket classes covered

A release usually contains a mix of:

- **Migration tickets** — carry Firebase / DB writes. Have a folder under `tickets/{KEY}/` with `deploy.md`, `session-log.md`, and/or `deploy-result.md`. Discovered automatically by Step 2.
- **Code-only tickets** — ship via a PR merged to `main` / `develop`. No `tickets/{KEY}/` folder. The user supplies these keys at runtime (Step 2a).

The report lists both, with a `Type` column / line so the reader can tell them apart. Status detection differs per class — see Step 3 (migration) and Step 3e (code-only).

Title format (both local heading and Confluence title):

```
Release Report: {DD MMM YYYY}
```

Example: `Release Report: 12 May 2026`

---

## Prerequisites

- The repo's `tickets/` directory exists and contains at least one ticket folder.
- The user can supply the release date as `DD MMM YYYY` (skill prompts if omitted).
- The user can supply the Confluence parent page ID for releases on first run (skill prompts).

---

## Step 1: Resolve the release date

Read the skill argument.

- If the argument is empty or malformed, ask: `Which release date? (DD MMM YYYY, e.g. 12 May 2026)`
- Parse it to ISO `YYYY-MM-DD` for the local filename, and keep the display form `DD MMM YYYY` for the title.

If the user supplies a relative date ("yesterday", "today", "this week"), convert to an absolute date using the current date from the environment context, then echo the resolved date back for confirmation before continuing.

---

## Step 2: Discover ticket folders

Run a Bash listing of `tickets/`:

```
ls -d tickets/*/ 2>/dev/null
```

For each directory:

| Files present | Classification | Include in report? |
|---|---|---|
| `rca.md` only | RCA-only (investigation, no deploy) | No — silently skip; do NOT mention in the report |
| `deploy.md` only | Planned, not yet deployed | Yes — status `Pending` |
| `deploy.md` + `session-log.md`, no `deploy-result.md` | Deployed, no formal result doc | Yes — status from session-log |
| `deploy.md` + `deploy-result.md` | Deployed, formal result | Yes — status from deploy-result |
| `deploy.md` + `session-log.md` + `deploy-result.md` | Deployed with both | Yes — prefer deploy-result for status |
| Empty / no recognised files | Anomalous | Skip silently; do NOT mention in the report |

User-requested skips (release manager names a ticket as out-of-scope during the conversation): silently omit. Do NOT add an "Out-of-scope tickets noted in the workspace" subsection to the appendix — readers of the release report only care about what shipped this cycle, not what didn't.

Build an in-memory ticket list with: `ticket_key`, `class: "migration"`, `local_files[]`, `classification`.

---

## Step 2a: Collect code-only tickets from the user

Many releases also include tickets whose entire delivery is a PR merge — no Firebase writes, no `tickets/{KEY}/` folder. Prompt the user:

```
Are there code-only tickets in this release (PR-merged to main, no /tickets folder)?

Paste keys comma-separated, e.g. "GEN-1303, GEN-2653, FIR-117", or reply 'none'.
```

Parse the response:

- `none` (or empty) → skip Step 3e entirely; continue with migration tickets only.
- A list of keys → validate each matches `(GEN|FIR|IVC|PARK)-\d+`. Drop invalid tokens with a one-line warning (`Skipped invalid key: 'XXX'`). Add the surviving keys to the in-memory ticket list with `class: "code-only"`, `local_files: []`.

**Deduplicate against migration tickets.** If a user-supplied key is already discovered under `tickets/`, do NOT add a duplicate entry — keep the migration record and tell the user: `'{KEY}' already has a /tickets folder; treated as a migration ticket, ignoring the code-only entry.`

---

## Step 3: Detect status per ticket

For every included ticket, derive these fields from the local files. Do NOT call Firebase. Do NOT modify any file.

### 3a — From `deploy.md` (always present for included tickets)

Read at minimum the first 30 lines. Extract:

| Field | Where to look |
|---|---|
| Ticket title | First-line `# ` heading, strip the leading ticket key prefix |
| Jira URL | First `https://invocarecompass.atlassian.net/browse/{KEY}` link |
| Target environment | `**Target environment:** {ENV}` line — typically `uat`, `prod`, or `dev` |
| Fix type | `**Fix type:** {VALUE}` line if present — `config`, `code`, or `Mixed` |
| Prepared by | `**Prepared by:** {NAME}` or `**Author:** {NAME}` if present |
| Source page | `**Source:** Confluence — …` link if present |

### 3b — From `deploy-result.md` (if present)

Read the "Outcome at a Glance" table (typically lines 15–35). Extract:

| Field | Pattern |
|---|---|
| Run mode | `**Run mode:** **REAL**` vs `**DRY-RUN**` |
| Run date | `**Run date:** {DATE}` |
| Status | The `Status` row in the Outcome table: `✅ PASS` → `Success`; `❌ FAIL` / `⚠️ partial` → `Failed`; absence of a clear PASS → `Pending` |
| Run by | `**Run by:** {NAME}` |

If the doc carries a `## Run N` header for multiple runs, use the **latest** run's status for the ticket's bucket (Step 5). If the latest run is a `revert` and there is no later `apply`, the bucket status is `Failed (rolled back)`.

### 3b-ii — Build the full session-state history (`deploy_history[]`)

A `deploy-result.md` is a cumulative ledger: it records every deploy session across all runs, not just the latest. For each ticket that HAS a `deploy-result.md`, build a `deploy_history[]` list — one entry per session — so the report can show the full deploy history inline, not just the collapsed bucket status.

Read the **Session Ledger** section (the `## Session Ledger` heading; "Write sessions" and "Rollback sessions" fenced blocks). Each row there is one session: `action | env | session_id | date | DB`. For every row capture:

| Field | Source | Notes |
|---|---|---|
| `env` | the `env` column | `dev` / `uat` / `prod` |
| `action` | the `action` column | `apply` / `re-apply` / `revert` |
| `date` | the date column | `YYYY-MM-DD` (drop the time for the report) |
| `status` | cross-reference the matching run's `Status` row (Outcome at a Glance for Run 1, the `## Run N` Status line for later runs) | `✅` apply with a PASS → `Success`; `⚠️`/`❌` → `Failed`/`Partial`; a `revert` row → `Rolled back` regardless of the run's PASS/FAIL |
| `session_id` | the `session_id` column | captured for the **local draft only** — see the strip rule below |

**Session IDs are PUBLISHED inline (release-report carve-out).** Capture each session id and render it inline in its own deploy-history row as the `{session_id}-` prefix on the action field (Step 6). Per the `/create-release-report` carve-out in `output-guardian.md`, these `Deploy history:` rows are the ONE place session IDs are permitted on a Confluence page — on BOTH the local draft and the published page — because they are the per-session rollback reference. Session IDs remain barred everywhere else in the report: they may appear ONLY in `Deploy history:` rows, never in the executive summary, notes, or appendix prose.

Fallbacks:
- **Dry-run ledger** (`n/a — dry-run (no sessions created)`): record `deploy_history: []` and leave the inline history off — there are no real sessions to list.
- **No Session Ledger section** (older `deploy-result.md` predating the ledger): synthesise a single entry from the top-level `Target environment` + `Run mode` + `Run date` + bucket status, and note `deploy_history: reconstructed` so Step 6 can flag it.

Order `deploy_history[]` chronologically (oldest run first), so the inline list reads as the deploy progressed.

### 3c — From `session-log.md` (if no deploy-result.md)

Scan for the latest `## Run N — {ENV} — {DATE TIME}` header (highest N). Read its `Action: …` line:

| Latest `Action:` | Status |
|---|---|
| `apply` or `re-apply` | `Success` |
| `revert` (with no later re-apply) | `Failed (rolled back)` |
| any other action | `Pending` and add a one-line note in the appendix |

### 3d — RCA presence

Check whether `rca.md` exists alongside the deploy files. If yes, record `rca_local: true` (used in the report to flag "RCA published" tickets). Do NOT copy any local artifact path into the report body.

### 3e — Code-only ticket status (no local files)

For every `class: "code-only"` ticket from Step 2a, there is no local report to read — but Jira status is **not** the source of truth here either. The release manager's act of naming the ticket in Step 2a is the assertion that it is part of this release.

Default status:

- `class: "code-only"` → status `Success` (inclusion = assertion of shipped)

If the release manager wants to override a code-only ticket's status, they can edit the draft in the Step 7 review loop and move the entry between buckets manually — Step 7's re-summarise trusts the file as the source of truth.

Jira metadata fetched in Step 4 (summary, assignee, fixVersions) and the PR link from Step 4b are **enrichment only** — they populate the per-ticket line but do not affect status classification. Specifically, a code-only ticket whose Jira state is still `In Progress` / `Build in progress` / `FIX IN PROGRESS` is NOT downgraded to `Pending` on that basis alone; Jira workflow states routinely lag the actual deploy state in this team's process.

If `getJiraIssue` fails for a code-only ticket, keep `Success` but record `jira_fetch: failed` and surface it in the appendix. Do NOT bucket under Skipped on that basis.

---

## Step 4: Enrich each ticket from Jira

For every included ticket key (both classes), fetch metadata once:

```
getJiraIssue(
  cloudId: "invocarecompass.atlassian.net",
  issueIdOrKey: "{TICKET_KEY}",
  fields: ["summary", "fixVersions"]
)
```

If the call fails for a ticket: keep going, record `jira_fetch: failed` against that ticket, and note it in the appendix. Do NOT abort the whole report on a single Jira fetch failure.

From the response capture:

- `summary` — overwrite the local-derived title if Jira's is cleaner
- `fixVersions[]` — for the optional "Fix version" cluster in the executive summary

Do NOT fetch `status` (Jira workflow state is not consulted for classification per Step 3) or `assignee` (intentionally not displayed in the report).

### 4a — Locate the Technical Approval (TA) comment

For each **migration** ticket, search Jira comments for the TA. Pattern in this team: the most recent comment by the tech lead that contains "Technical Approach" or "TA" in the first 200 chars, OR a comment explicitly linked from the deploy.md `Origin Jira comment:` line.

Strongly prefer the `focusedCommentId` already captured in `deploy.md` — that is the canonical TA link. If not present in `deploy.md`, leave the TA cell as `❌ missing` (do NOT guess).

Code-only tickets have no TA convention — they render `PR:` only (see 4b). Migration tickets always render `TA:`.

### 4b — PR line for any ticket whose Type includes "Code"

If a ticket's `Type` (per Step 5) contains the word `Code` — i.e. `Code + Config`, `Code (deployed)`, or `Code (PR merge)` — the per-ticket entry MUST include a `PR:` line. Render it as:

```
PR: [TBD]
```

The release manager fills in real PR URLs during the Step 7 review loop. Do NOT attempt to extract PR URLs from the deploy.md, do NOT call any Jira PR-lookup API, do NOT guess. The skill's job is to surface where input is needed; the human's job is to supply it.

> **Why `[TBD]` specifically:** the Output Guardian linter (Step 8) blocks publish when `[TBD]` appears in the body (L8 — empty placeholder leakage). This guarantees no release report is published while a PR line is still unfilled.

Tickets whose Type does not contain "Code" (e.g. `Config`, `Config (Firestore)`) MUST NOT have a `PR:` line — the PR concept does not apply to pure config releases.

---

## Step 5: Group tickets by outcome

Bucket every included ticket (both classes) into one of:

- **✅ Success** — status `Success` from Step 3 / 3e
- **❌ Failed** — status `Failed` or `Failed (rolled back)` from Step 3 / 3e
- **⏳ Pending** — status `Pending` from Step 3 / 3e
- **➖ Skipped** — anomalous folders (no recognised files), or `jira_fetch: failed` AND no local title

Within each bucket, sort by ticket key ascending. Tag each entry with its `class` so the renderer can show the `Type` line:

| `class` | `Type` label rendered |
|---|---|
| `migration` | `Config` if `Fix type: config`; `Code + Config` if `Mixed`; `Code (deployed)` if `Fix type: code` |
| `code-only` | `Code (PR merge)` |

---

## Step 6: Draft `release-report-{YYYY-MM-DD}.md` locally

Write to repo root: `release-report-{YYYY-MM-DD}.md`. Use this structure (mirrors the existing draft conventions; adds a `Type` line per ticket so migration vs. code-only is visible):

```markdown
# Release Report — {DD MMM YYYY}

**Total tickets:** {N}
**Success:** {S}  ·  **Failed:** {F}  ·  **Pending:** {P}  ·  **Skipped:** {K}

<!-- Code-only ticket keys captured this run (used by 'edit done' re-summarise): {COMMA-SEP LIST OR 'none'} -->

## Executive summary

{1–2 paragraphs. State the headline outcome (N of M shipped). Distinguish migration vs. code-only deliveries. Call out any common root-cause clusters across the migration set, and any cross-cutting code changes (e.g. "FCRM-Web v3.2.x ships GEN-XXXX and GEN-YYYY as code-only"). No tool names. No session IDs.}

## Tickets by outcome

### ✅ Success ({S})

**[{TICKET_KEY}]({JIRA_URL}) — {SUMMARY}**
Type: {Config | Config (Firestore) | Code + Config | Code (deployed) | Code (PR merge)}
{TA_LINE_IF_MIGRATION_TICKET}
{PR_LINE_IF_TYPE_CONTAINS_CODE}
{DEPLOY_HISTORY_BLOCK_IF_DEPLOY_RESULT_PRESENT}
Notes: {one-line — headline change. For migration tickets, pull from the deploy.md "What This Does" first sentence (paraphrased). For code-only tickets, pull from the Jira summary / PR title.}
```

Rendering the `Deploy history:` block (only for tickets that had a `deploy-result.md`, i.e. `deploy_history[]` is non-empty):

```
Deploy history:
  - {env} | {session_id}-{action} | {status} | {date}
  - {env} | {session_id}-{action} | {status} | {date}
```

One bullet per `deploy_history[]` entry from Step 3b-ii, oldest first. Each row is `{env} | {session_id}-{action} | {status} | {date}`, pipe-separated, with the session id embedded as the `{session_id}-` prefix on the action field. These rows are **published as-is** — the `/create-release-report` carve-out in `output-guardian.md` permits session IDs in `Deploy history:` rows on the Confluence page, so the body is published verbatim (no strip). If `deploy_history: reconstructed` (no real session id), render the row as `{env} | {action} | {status} | {date}` with no `{session_id}-` prefix, and append ` _(history reconstructed from summary — no session ledger)_` to the `Deploy history:` header line. Tickets with no `deploy-result.md` (status came from `session-log.md`, or code-only tickets) get NO `Deploy history:` block.

Example block:

```
Deploy history:
  - dev | 481-apply | Success | 2026-05-20
  - uat | 487-apply | Success | 2026-05-26
  - uat | 489-revert | Rolled back | 2026-05-27
  - uat | 492-re-apply | Success | 2026-05-28
```

Rendering rules for the `TA:` and `PR:` lines:

| Class | Type contains "Code" | Lines rendered |
|---|---|---|
| migration | no | `TA: {link or ❌ missing}` |
| migration | yes | `TA: {link or ❌ missing}` + `PR: [TBD]` |
| code-only | yes (always) | `PR: [TBD]` — release manager MAY add a `TA:` line above it during review if a Jira `focusedCommentId` is known |

`[TBD]` is the user-fills-in marker — release manager replaces with the GitHub PR URL during Step 7. The Output Guardian linter blocks publish if any `[TBD]` remains in the body.

Code-only tickets are not given a default `TA:` line because they have no `deploy.md` from which to anchor the canonical TA `focusedCommentId`. If the release manager already knows the TA comment ID, they paste it in during review using the same format as migration tickets: `TA: [Jira comment <N>](https://invocarecompass.atlassian.net/browse/<KEY>?focusedCommentId=<N>)`.

Example renderings:

```
**[GEN-2543](...) — Mortuary Screen columns**
Type: Config
TA: [Jira comment 159112](...)
Deploy history:
  - dev · apply · Success · 2026-05-08
  - uat · apply · Success · 2026-05-11
Notes: ...

**[GEN-1747](...) — BCP Run Sheet**
Type: Code + Config
TA: [Jira comment 159059](...)
PR: [TBD]
Deploy history:
  - uat · apply · Success · 2026-05-12
Notes: ...

**[GEN-2766](...) — PreNeed Screen scroll fix**
Type: Code (PR merge)
PR: [TBD]
Notes: ...

{... repeat per ticket, blank line between ...}

### ❌ Failed ({F})

{... same shape; add `Reason:` line with the failure description ...}

### ⏳ Pending ({P})

{... same shape; add `Status:` line with what's blocking ...}

## Data migration scripts

{Inventory any standalone migration scripts. If all migration tickets are Firestore/RTDB config writes documented in TA comments, say so explicitly. List tickets carrying code changes by repo (e.g. "FCRM-Web — GEN-XXXX, GEN-YYYY"); include code-only tickets in this list too if you can identify the repo from the PR URL. Do NOT paste session IDs or local paths.}

## Appendix: methodology

Outcomes were classified as follows:

- **Success:** {definition mirrored from Step 5}
- **Failed:** {…}
- **Pending:** {…}
- **Skipped:** {…}

Ticket classes:

- **Migration:** discovered automatically under `tickets/` in the working copy. Status read from `deploy-result.md` (preferred) or the latest run in `session-log.md`. **Jira workflow state is not consulted.** Where a `deploy-result.md` exists, every deploy session it records (across all runs — apply, re-apply, revert) is listed inline under the ticket as a `Deploy history:` block, one row per session showing the environment, session id, action, outcome, and date. The session id is the per-session rollback reference and is published in the row per the release-report carve-out.
- **Code-only:** supplied by the release manager at report-generation time. Status defaults to `Success` because inclusion in the release list IS the assertion of shipping. Jira metadata and linked PR(s) are surfaced for traceability only — they do not affect the bucket. If the release manager wants a different status, they edit the draft directly during review.

{If any tickets had Jira-fetch failures, missing TAs, or missing PR links, list them in a sub-section here.}
```

> **Why the HTML comment with code-only keys:** lets the skill recover the code-only ticket list if the user replies `edit done` and the in-memory state is stale. Step 7 re-reads that comment to rebuild the list before re-summarising.

Once written, print:

```
Drafted: release-report-{YYYY-MM-DD}.md
  {N} tickets total — {MIG} migration · {CODE} code-only
  Outcomes: {S} success · {F} failed · {P} pending · {K} skipped
  TA links: {TA_RESOLVED}/{MIG}  ·  PR links: {PR_RESOLVED}/{CODE}

Review the draft. When ready, reply:
  - "publish" to push to Confluence
  - "edit done" after you've edited the file and want to re-summarise
  - "cancel" to stop here
```

Wait for the user's response.

---

## Step 7: Handle the review loop

| User reply | Action |
|---|---|
| `publish` | Continue to Step 8 |
| `edit done` | Re-read the file. Parse the `<!-- Code-only ticket keys captured this run: ... -->` HTML comment to recover the code-only list (so the in-memory state survives across edits). Regenerate per-bucket counts from the file's bucket headers (`### ✅ Success (N)`, etc.) — if the user removed or added entries, the new counts come from the file, not from the original scan. Print updated summary. Ask again. |
| `cancel` | Stop. Print: `Stopped — local draft kept at release-report-{YYYY-MM-DD}.md.` Exit. |

Loop on `edit done` until the user says `publish` or `cancel`.

> **Why parse counts from the file instead of re-scanning:** the user may have manually moved a ticket between buckets (e.g. promoted a Pending to Success because they verified it post-draft) or added a ticket the skill missed. Trust the file as the source of truth on re-summarise.

---

## Step 8: Pre-publish Output Guardian linter

Before any Confluence call, gate the assembled body through the shared linter.

> **Session IDs are published as-is (no strip).** Per the `/create-release-report` carve-out in `output-guardian.md`, session IDs embedded in `Deploy history:` rows (`{env} | {session_id}-{action} | …`) are permitted on the Confluence page. The linter's L3 Carve-out B recognises these rows and does NOT flag them — but it STILL blocks a session ID that appears anywhere else (executive summary, notes, appendix prose). The body is published verbatim; there is no separate stripped publish body.

1. Re-read `release-report-{YYYY-MM-DD}.md` from disk (the user may have edited it during Step 7). This is the body — published verbatim.
2. Read the shared linter prompt at `.claude/skills/_shared/contracts/output-guardian-linter.md`.
3. Dispatch a `pipeline-checker` subagent (`.claude/agents/pipeline-checker.md`) with:
   - The full prompt from the shared linter
   - `host: "confluence-page"`
   - `ticket_key`: `null` (this skill is not per-ticket; the linter MUST handle `null`)
   - `body`: the full content of the local draft (Deploy history session IDs intact — Carve-out B permits them; a session ID in prose is still a blocker)
4. Parse the JSON result block per `.claude/skills/_shared/contracts/checker-contract.md`: `{ verdict, host, ticket_key, summary, iteration_hint, gaps[] }`.
5. Branch on verdict:
   - **FAIL** → print every blocker gap with its `body:line` evidence. Refuse to publish. Print: `Release report NOT published — Output Guardian linter detected blockers. Fix the local draft and reply 'edit done' to re-summarise, then 'publish' to retry.` Loop back to Step 7.
   - **WARN** → print every warning gap. Ask `Proceed anyway? (yes/no)`. If `no` → loop back to Step 7. If `yes` → continue.
   - **PASS** → continue silently.

If the linter dispatch fails or returns malformed JSON: print `Output Guardian linter could not run: <reason>.` Ask `Proceed without the linter? (yes/no)`. If yes, record `Linter: SKIPPED (dispatch failure)` in the Step 11 summary; if no, exit.

This linter runs ONCE per publish attempt — no iteration.

---

## Step 9: Resolve the Confluence parent

The release-report parent page in KMS2 is NOT hardcoded — release pages live under a release-notes parent the team picks per cycle.

1. If the user has previously supplied a parent page ID in this conversation, reuse it.
2. Otherwise prompt: `Confluence parent page ID for release reports in KMS2? (paste the page ID, e.g. 327231504407)`
3. Validate the ID by fetching the parent page once:

```
getConfluencePage(
  cloudId: "invocarecompass.atlassian.net",
  pageId: "{PARENT_ID}"
)
```

- If the fetch fails: surface the error, ask for a corrected ID, retry once. After two failures, exit and tell the user to verify the page exists in space KMS2.
- If the fetch succeeds: confirm the parent title to the user before publishing — `Publishing under: "{PARENT_TITLE}" (KMS2). Confirm? (yes/no)`.

---

## Step 10: Search for existing release page, then create or update

### 10a — Search

```
searchConfluenceUsingCql(
  cloudId: "invocarecompass.atlassian.net",
  cql: "title = \"Release Report: {DD MMM YYYY}\" AND space = \"KMS2\" AND type = page",
  limit: 5
)
```

### 10b — Branch

| Match | Action |
|---|---|
| No page found | Create new (10c) |
| Exactly one page found | Show title + last-modified to user. Ask `Existing page found, update it? (yes/no)`. If yes → update (10d). If no → exit without publishing. |
| Multiple pages found | List all candidates. Ask the user to pick one to update or `new` to create a fresh page. |

In both 10c and 10d, `content` is the full content of the local draft `release-report-{YYYY-MM-DD}.md`, published verbatim — Deploy history session IDs are kept per the carve-out. The Confluence create/update tools require the numeric `spaceId` for KMS2 (resolve it once via a spaces lookup), not the space key. Use `contentFormat: "markdown"`.

### 10c — Create

```
createConfluencePage(
  cloudId: "invocarecompass.atlassian.net",
  spaceId: "{KMS2_SPACE_ID}",
  parentId: "{PARENT_ID}",
  title: "Release Report: {DD MMM YYYY}",
  contentFormat: "markdown",
  body: "{full content of release-report-{YYYY-MM-DD}.md}"
)
```

### 10d — Update

```
updateConfluencePage(
  cloudId: "invocarecompass.atlassian.net",
  pageId: "{EXISTING_PAGE_ID}",
  title: "Release Report: {DD MMM YYYY}",
  contentFormat: "markdown",
  body: "{full content of release-report-{YYYY-MM-DD}.md}",
  version: {current_version + 1}
)
```

> **Why update instead of delete+create:** preserves the page URL so any existing Jira/Confluence links keep working.

---

## Step 11: Save the URL back into the local draft

After publish succeeds, prepend the Confluence URL to the local file. Edit the local file in place:

After the `# Release Report — {DD MMM YYYY}` heading, insert (if not already present):

```markdown
**Confluence:** [{TITLE}]({CONFLUENCE_PAGE_URL})
```

If the line already exists (skill was re-run for an update), edit it in place to the new URL — do NOT add a duplicate line.

---

## Step 12: Summarise to the user

Print:

```
✅ Release report published.

Title:      Release Report: {DD MMM YYYY}
Action:     {created | updated}
Confluence: {URL}
Local file: release-report-{YYYY-MM-DD}.md
Linter:     {PASS | WARN with acknowledged gaps | SKIPPED (reason)}

Counts:     {N} tickets — {MIG} migration · {CODE_ONLY} code-only
Outcomes:   {S} success · {F} failed · {P} pending · {K} skipped
TA links:   {TA_RESOLVED}/{MIG} resolved · {ta_missing_count} marked '❌ missing'
PR lines:   {filled_count}/{CODE_TYPED_COUNT} filled by release manager  ({remaining_tbd} still '[TBD]')
```

Do NOT include tool names, session IDs, or any internal-tooling references in the summary.

---

## Quality Bar

- [ ] Release date resolved before any scan
- [ ] Every ticket folder under `tickets/` was classified per the rubric in Step 2
- [ ] User was prompted for code-only ticket keys (Step 2a) — answer captured (a list, or 'none')
- [ ] Code-only keys were validated against `(GEN|FIR|IVC|PARK)-\d+` and deduplicated against migration tickets
- [ ] RCA-only folders (only `rca.md`) were skipped from the report (but may still be mentioned in the appendix if relevant)
- [ ] Migration ticket status was derived from local files only — no Firebase calls, no inferences from absent data
- [ ] Every ticket with a `deploy-result.md` renders a `Deploy history:` block, one row per session (`{env} | {session_id}-{action} | {status} | {date}`, oldest first), published verbatim to Confluence per the carve-out
- [ ] Session IDs appear ONLY in `Deploy history:` rows — never in the executive summary, notes, or appendix prose (the linter blocks those)
- [ ] Code-only tickets default to Success — Jira workflow state was not consulted for classification
- [ ] Every ticket whose Type contains "Code" has a `PR: [TBD]` line (or a release-manager-filled URL after review) — pure Config tickets do NOT have a PR line
- [ ] No PR URLs were auto-extracted, guessed, or fetched from Jira remote links — PR lines are release-manager input only
- [ ] Each ticket renders a `Type` line so the reader can distinguish migration vs. code-only
- [ ] Jira fetch failures were tolerated per-ticket and logged in the appendix
- [ ] The code-only ticket list is preserved in the local draft via HTML comment so `edit done` doesn't lose it
- [ ] Local draft was written before any Confluence call
- [ ] User explicitly approved publish before the Confluence API was called
- [ ] Output Guardian linter ran with verdict captured (PASS / WARN-acknowledged / SKIPPED-with-reason)
- [ ] Existing Confluence page was searched before creating a new one (idempotent)
- [ ] No tool names, session IDs, or local artifact paths in the report body or Confluence page
- [ ] Confluence URL persisted back into the local draft
- [ ] Space key `KMS2` used; parent ID validated via a read before publishing
- [ ] Read-only against Firebase — no `write_rtdb`, `write_firestore`, or session create/complete/rollback was issued

---

## Next step

After completing this skill, print this block to the user before ending.

```
---
**Next step**

The release report is published. Common follow-ups:

- Share the Confluence URL in the team's release channel
- For each Pending ticket, run /task-status {TICKET_KEY} to check whether it shipped late
- For each Failed ticket, run /create-rca {TICKET_KEY} (if no RCA exists) to capture root cause
---
```
