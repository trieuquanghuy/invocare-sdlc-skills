---
name: ticket-comment
description: "Use when posting what was done on a completed ticket — after the work is applied and ready for testing. Default produces the FULL QA-handoff comment; pass `--short` (or the bare token `short`) for the dev/UAT progress checkpoint with rollback session IDs. Trigger on: post comment, comment on ticket, write Jira comment, post fix, document what changed, what we did on the ticket, short comment, progress comment."
argument-hint: "Jira ticket key (e.g. GEN-2680, IVC-123, PARK-456). Append `--short` (or `short`) to produce the dev/UAT progress checkpoint instead of the full QA-handoff comment."
disable-model-invocation: true
---

# Jira Done Comment

Post a structured comment documenting what was actually done on a ticket. This is posted AFTER the work is done — the ticket is ready for testing.

**Output guardian:** all output reads as written by a developer. Apply `.claude/rules/output-guardian.md` — never include tool names, session IDs, or any indication of automation.

## When to Use

- After completing work on a ticket — to document what changed for testers and reviewers
- When asked to "comment on the ticket" or "post what we did"
- Works with any Jira project prefix (GEN, IVC, PARK, etc.)

## This is NOT

- A fix proposal or recommendation — the work is already done
- An RCA — the ticket should already have one if it's a bug (if not, run `create-rca` first)
- An estimation — the work is done, the ticket moves to testing

## Workflow

### Step 0: Read Jira Ticket

Fetch the ticket via Atlassian MCP to get:
- **Issue type** (Bug, Story, Task, Sub-task, etc.)
- **Summary and description**
- **Acceptance criteria** (for stories)
- **Comments** (check for existing RCA)
- **Assignee and Reporter** (accountId + displayName — used by the short template's `cc:` line)

Route based on issue type — this picks the FULL template flavor (Step 5 onward), not the short-vs-full decision:
- **Bug / Defect** → Bug template
- **Everything else** (Story, Task, Sub-task, etc.) → Feature template

### Step 0b: Decide Short vs Full Template

**Default is FULL.** SHORT is opt-in only — the user must signal it explicitly.

Scan `$ARGUMENTS` for either of:

- The flag form: `--short` (case-insensitive, anywhere in args)
- The bare token form: a standalone `short` token (case-insensitive) appearing as its own argument — e.g. `/ticket-comment GEN-2759 short`. A `short` substring inside another token (`shortlist`, `short-circuit`) does NOT count.

If either form is present → **SHORT template selected**.
Otherwise → **FULL template selected** (this is the default; no flag, no ambiguity).

Also accept the explicit opposite for symmetry: a `--full` flag is a no-op (it just confirms the default). Do not let `--full` and `--short` coexist — if both are present, refuse: `Both --short and --full were passed; pick one. Default is FULL — drop the flag to use it.` and exit.

**If SHORT is selected:**

1. Read `tickets/{TICKET_KEY}/session-log.md`. SHORT requires at least one `apply` row (action=apply; revert / re-apply rows do not count). If the file is missing or has zero apply rows, refuse: `No apply session found for {TICKET_KEY}; SHORT comment requires the rollback reference. Run /apply-fix first, then re-run with --short. Or drop --short to post the full template.` and exit.
2. Read [short-template.md](references/short-template.md).
3. Assemble the body per its field rules (NOUN from issue type, ENV_UPPER from the **most recent** `apply` row's env, CC_LIST from assignee + reporter + role tail, SESSION_ROWS from every `apply` row in chronological order).
4. **Skip Step 1, Step 2, Step 3, Step 4.** They are full-template concerns (RCA lookup, gap analysis, dev verification narrative). SHORT's verification surface is "the deploy happened; the session id below proves it".
5. Go directly to **Step 5a** (Output Guardian linter) → **Step 5** (post via `addCommentToJiraIssue`) → **Next step** decision tree.

**If FULL is selected (default):**

Continue with Step 1 onward as written. FULL does not depend on session-log.md for its template shape (only on Jira issue type → bug-template.md vs feature-template.md), though Step 1 still reads session-log.md for context if it exists.

> **Why opt-in:** FULL is the canonical post-fix comment shape — readable by leaders, BA, PM, QA, deployer. SHORT is a deliberately stripped progress checkpoint useful when you want the rollback session ids inline without the full QA-handoff narrative (typically after a dev or UAT apply, when QA isn't ready yet). Making SHORT opt-in means a routine `/ticket-comment GEN-1234` keeps producing the comprehensive comment; nobody gets a one-liner by accident.

### Step 1: Read Ticket Folder

Read ALL files in `tickets/{TICKET_KEY}/` — this is the **primary source** for assembling the comment:

- `rca.md` — root cause analysis, identifies what’s broken and why
- `spec.md` — technical approach, planned changes and deployment steps
- `*.sh` — fix scripts, migration scripts
- `*.json` — backups, config snapshots

> These local files are INPUT for assembling the comment. The Jira comment itself must NEVER reference local filenames (no "see spec.md", "see deploy.md", etc.). Write all content inline.

Everything in that folder tells the story of what was done. The comment is assembled FROM these artifacts.

Git history and current conversation are **secondary** — used to fill gaps if the folder doesn't have everything.

If the folder is empty or doesn't exist, assemble from git history and current conversation context. Flag to the user that the comment may be less complete without ticket artifacts.

### Step 2: Check for RCA

Search these locations in order — stop at first match:

1. **`tickets/{TICKET_KEY}/rca.md`** — check for a `**Confluence RCA:**` line at the top. If a URL is there (written by `publish-rca`), use it directly. If the placeholder `<!-- publish-rca writes URL here -->` is still there, move to step 2.
2. **Confluence** — search using `searchConfluenceUsingCql` with `title ~ "{TICKET_KEY}" AND type = page`. If found, use the Confluence page URL.
3. **Jira ticket comments** — look for comments with "Root Cause" or "RCA" headings

> If RCA exists locally but has no Confluence URL, suggest running `/publish-rca {TICKET_KEY}` to publish it before commenting.

RCA pages exist for **both bugs and stories/features** (e.g., investigation of export issues, data analysis before implementation).

If **no RCA found anywhere and ticket is a bug**: run the `create-rca` skill first. For stories, RCA is optional — proceed without it if not found.

If **RCA found**: read it. Include the RCA link in Section 1 (Before the Fix / Requirement). Use the RCA to understand what was broken — the "Not Addressed" comparison comes from what was planned vs done (Step 3).

### Step 3: Identify "Not Addressed" Items

Compare what was planned vs what was actually done:

- **Bug**: diff what was planned (from ticket folder or conversation context) against what was actually done. If no plan exists, fall back to RCA findings.
- **Story/Feature**: diff Jira acceptance criteria against what was actually done

Any gap = "Not Addressed" item. For each, note WHAT wasn't done and WHY (separate concern, blocked, deferred to another ticket, etc.).

### Step 4: Verify on Dev

Before posting the comment, confirm the changes are live on dev using available tools (do not name the tools in the comment):

- **Config changes**: confirm the updated paths/values are in place
- **Code changes**: confirm the relevant commits are deployed to dev
- **Config-only fix**: note in the comment: "Config-only fix, no code deployment required."

QA tests on dev first.

### Step 5: Post the Comment

Use the appropriate template.

### Step 5a: Pre-post Output Guardian linter

Before calling `addCommentToJiraIssue`, gate the assembled comment body through the linter subagent. The linter runs the same rubric for both short and full templates — the L3 carve-out in `.claude/rules/output-guardian.md` applies automatically when the body contains a `**Session deploy**` heading.

1. Read the shared linter prompt: `.claude/skills/_shared/contracts/output-guardian-linter.md`.
2. Dispatch a `pipeline-checker` subagent (`.claude/agents/pipeline-checker.md`) with:
   - The literal instruction `Apply .claude/rules/output-guardian.md and .claude/rules/secrets-safety.md to all output you produce.` (per `agents-safety.md` A1 — the subagent inherits both rules)
   - The full prompt from the shared linter
   - `host: "jira-comment"`
   - `ticket_key`: the current ticket key
   - `body`: the fully-assembled comment body (from the short template assembled in Step 0b, OR the full template assembled in Step 5)
3. Parse the JSON result block per `.claude/skills/_shared/contracts/checker-contract.md`: `{ verdict, host, ticket_key, summary, iteration_hint, gaps[] }`.
4. Branch on verdict:
   - **FAIL** → print every blocker gap with its body:line evidence. Refuse to post. Print: `Comment NOT posted — Output Guardian linter detected blockers. Address them in the assembled body and re-run /ticket-comment {TICKET_KEY}.` Exit.
   - **WARN** → print every warning gap. Ask `Proceed anyway? (yes/no)`. If `no` → exit. If `yes` → continue.
   - **PASS** → continue. Per `agents-safety.md` A3, do NOT trust the PASS blindly — spot-check the body yourself for the obvious banned tokens (tool names like `firebase-explorer` / MCP ids, AI/Claude attribution, local artifact paths, and any session ID sitting OUTSIDE a `**Session deploy**` block) before posting. If the spot-check finds a leak the linter missed, treat it as FAIL.

If the checker dispatch fails or returns malformed JSON: print `Output Guardian linter could not run: <reason>. Without it, no automated check that the comment is free of internal language.` Then ask `Proceed without the linter? (yes/no)`. Capture the linter status in the Step 6 summary as `Linter: SKIPPED (dispatch failure: <reason>)`.

This linter runs ONCE per `/ticket-comment` invocation — it does not iterate.

---

## Templates

Step 0b decides SHORT vs FULL by scanning `$ARGUMENTS` for `--short` / `short`. Default is FULL. Then pick the template:

- **SHORT (opt-in via `--short` or `short`; any issue type)** → [short-template.md](references/short-template.md)
- **FULL — Bug / Defect** (default for bug-type issues) → [bug-template.md](references/bug-template.md)
- **FULL — Everything else** (Story, Task, Sub-task) → [feature-template.md](references/feature-template.md)

The short template is a 4-line progress checkpoint with `cc:` and `Session deploy` rows; the full templates are the comprehensive QA-handoff comments. The two flavors do NOT mix — Step 0b picks exactly one.

## Template Rules

**Before the Fix / Requirement section:** Always start by stating what the correct behavior should be per the requirements. This gives readers the baseline to judge the fix against. For bugs, contrast it with the broken state. For features, reference acceptance criteria.

**Expected Result section:** Brief and concrete — what the user/system will now do differently. This is NOT a repeat of the fix details. It's the outcome in user-facing terms that dev and QA can verify.

**Verification section covers both Dev and QA.** Dev confirms the fix is deployed and config is in place. QA follows test scenarios on dev: what to do, what to expect. Include a regression check scenario.

**Impact Area section:** Always include. Derive from what the investigation found (affected paths, adjacent features) and what was changed. Three row types:
- **Direct fix** — the thing that was actually fixed
- **Regression risk** — features that share the same config path, form, or code area
- **May be affected** — loosely related areas worth a spot check

Populate "QA: What to Check" with a specific action (e.g. "generate Death Certificate export, confirm filename"). Populate "BA: What to Know" with business workflow context (e.g. "affects all teams using the standard funeral form"). Keep each cell to one sentence.

**Not Addressed section:** Only include if there are items that were deferred or descoped. Omit the section entirely if everything was done. Use the table format with both **Reason** (why not done) and **Follow-up** (what happens next — ticket, next sprint, needs BA input). Include location (e.g., Page 3) for context.

**Session Deploy section (FULL only — required):** Always populate. Pull rows from `tickets/{TICKET_KEY}/session-log.md`, filtering to `action=apply` only (drop `revert` / `re-apply` rows). Render chronological — earliest apply first. Use the same row shape as the short template (canonical spec in `short-template.md`):

- **List bullets only**, never a table. A line like `| Env | Session | Applied at (Sydney) |` is forbidden — it adds column-header noise and the timezone label drifts the format.
- Row format: `- {env}: {session_id} — {YYYY-MM-DD HH:MM} — {DB}`. Each row carries the session id, the apply timestamp, and the **target database**. Backticks around `{session_id}` optional (bare for short numeric IDs like `382`; backticked for longer alphanumeric / dashed IDs).
- **Target database (`{DB}`) is required** — one of `RTDB`, `Firestore`, or `RTDB+Firestore` (use the combined form when the session wrote to both). Derive it from the write tool recorded in `session-log.md`: `write_rtdb` → `RTDB`, `write_firestore` → `Firestore`. A row missing the `— {DB}` suffix is flagged by the linter.
- **No timezone label** on the timestamp. `2026-05-26 14:50` is correct; `2026-05-26 14:50 (Sydney)` invalidates the row at the linter.
- Keep the `**Session deploy**` heading verbatim — it's the marker that activates the Output Guardian carve-out in `.claude/rules/output-guardian.md`.

If `session-log.md` is missing or has zero apply rows, omit the section AND surface a warning to the user before posting (`No apply sessions found for {TICKET_KEY} — Session Deploy section omitted. Confirm the work was actually applied before posting.`); do NOT silently invent or guess.

**No `cc:` line in FULL templates.** The `cc: @assignee, @reporter, BA / PM / QA` line is a SHORT-template-only construct — it tags the next deployer + role inbox for an operational checkpoint. FULL is the QA-handoff comment; its audience is covered by the Audience section above (leaders, BA, PM, QA, UAT deployer) and does not need an inline mention list. Do not add a `cc:` line when assembling FULL; do not migrate the short template's cc convention into bug-template.md or feature-template.md.

**Screenshots section:** Feature template only. Now section 8 (after Session Deploy). Only include if screenshots or demo are available.

**UAT Deployment section:** Always include. Populate it based on fix type — keep only the matching block, delete the other two:

| Fix type | Block to keep | Key data sources |
|----------|--------------|-----------------|
| Config-only | "Config-only" block | Environment-specific IDs from investigation; acceptance criteria for verify step |
| Code-only | "Code-only" block | git log / PR URL → PR reference; pipeline name from project conventions |
| Mixed | "Mixed" block | Both of the above |

**How to populate the ENV_SPECIFIC ID table:**
For each environment-specific path, convert it to plain English in the comment:
- The "How to find in UAT" column must be human-readable — describe what to look for, not tool call syntax
- Example: "In UAT: find the record in `/teams/{TEAM_ID}/templates` where `label` = `"Standard Death Certificate"`"
- Include the dev value as a reference so the deployer knows what they're looking for

**Verify steps** (end of each block): write as plain app actions (e.g., "Open Funeral form, complete to Page 3, confirm export filename is `Death_Certificate.pdf`"). Never reference internal tools or local files.

**If no config changes**: omit ENV_SPECIFIC table, describe code-level verification only.

---

## Audience

This comment is read by **leaders, BA, PM, QA, and the UAT deployer**. Write for all of them:

- **Leaders/PM:** Want to know what changed and that it's ready for testing
- **BA:** Want to confirm the work matches requirements. "Not Addressed" gives them context on gaps without having to ask.
- **QA:** Want clear test scenarios to verify the work
- **UAT deployer** (dev team member or Claude in a new session): Jumps straight to "UAT Deployment" section — needs to know fix type, ENV_SPECIFIC IDs to resolve, exact steps, and rollback path

## Comment Rules

1. **Document what was done, not what should be done** — past tense, not proposals
2. **Code blocks show actual changes** — real old/new config or code, not pseudocode
3. **Quantify the impact** — percentages, record counts, concrete data
4. **Verification is for QA** — write test scenarios with steps QA can follow on dev, include regression checks, state config verification date
5. **"Not Addressed" is honest** — state what wasn't done and why. Don't hide gaps.
6. **Deviation from RCA** (bug only) — if the actual fix differed from RCA recommendation, say so
7. **No estimation** — the work is done
8. **No fix options** — there's only one outcome: what was actually done
9. **No new suggestions** — don't propose improvements or future work. This comment closes work, it doesn't open new work
10. **Verification section confirms, not suggests** — list what QA should verify, not new features or enhancements
11. **Never mention internal tools** — no firebase-explorer, session IDs, MCP tools, AI/Claude references, or any internal tooling. Write the comment as a developer would, not as an AI agent running tools.

## How to Post

Use Atlassian MCP `addCommentToJiraIssue` with `contentFormat: "markdown"`.

**Resolve `cloudId` first — it is a UUID, not the site domain.** Call `getAccessibleAtlassianResources` once and reuse the returned `id` (a UUID) for every subsequent call; do NOT hardcode the site domain string (`invocarecompass.atlassian.net`) as the `cloudId`.

```
mcp__plugin_atlassian_atlassian__getAccessibleAtlassianResources()
// → pick the InvoCare site; capture its `id` (a UUID), reuse it below

mcp__plugin_atlassian_atlassian__addCommentToJiraIssue({
  cloudId: "{CLOUD_ID_UUID}",
  issueIdOrKey: "{TICKET_KEY}",
  commentBody: "{formatted comment}",
  contentFormat: "markdown"
})
```

## Quality Bar

**Routing (both flavors):**

- [ ] Scanned `$ARGUMENTS` for `--short` / bare `short` token in Step 0b; treated absence as FULL (default)
- [ ] Refused on `--short` + `--full` collision with the documented message
- [ ] Picked exactly one of SHORT or FULL — never both, never neither

**SHORT flavor (skip when FULL was chosen):**

- [ ] Read `tickets/{TICKET_KEY}/session-log.md` and confirmed at least one `apply` row exists
- [ ] On `(no apply found)`: refused to post with the documented message; did not synthesize sessions; did not silently fall back to FULL
- [ ] NOUN derived from Jira issue type (bug / story / task / ticket) — no hardcoded "ticket"
- [ ] ENV_UPPER is uppercase `DEV` / `UAT` / `PROD` matching the most recent apply row's env
- [ ] cc list resolved at runtime: assignee (if any) + reporter (if different) + literal `BA / PM / QA`
- [ ] Session deploy rows: one bullet per `apply` row from session-log.md (NO revert / re-apply rows), in chronological order, each ending with the required `— {DB}` target-database field (`RTDB` / `Firestore` / `RTDB+Firestore`)
- [ ] No extra sections — body is exactly: headline + cc + `**Session deploy**` + N rows

**FULL flavor (skip when SHORT was chosen):**

- [ ] Read all files in `tickets/{TICKET_KEY}/` before assembling comment
- [ ] Detected ticket type from Jira and used correct template
- [ ] Correct requirement stated first — reader knows what "right" looks like before seeing the fix
- [ ] No `cc:` line in the body — `cc:` is a SHORT-only construct
- [ ] Section 7 Session Deploy populated from session-log.md (action=apply only, chronological), or section omitted with the documented warning when no apply rows exist
- [ ] Session Deploy rows are markdown LIST bullets (NOT a table); each row ends with the required `— {DB}` target-database field (`RTDB` / `Firestore` / `RTDB+Firestore`); timestamps have NO timezone label like `(Sydney)`; `**Session deploy**` heading written verbatim
- [ ] Code blocks show ACTUAL changes — not pseudocode or proposals
- [ ] Numbers are real (record counts, percentages from actual data)
- [ ] Expected Result section is brief, concrete, and testable — not a repeat of fix details
- [ ] Impact Area section populated — Direct fix row + at least 1 regression risk row — QA and BA columns filled with specific actions, not vague descriptions
- [ ] Dev verified changes are live before posting (queried Firestore/RTDB/code)
- [ ] Verification section has both Dev confirmation and QA test scenarios with Steps and Expected Results
- [ ] Includes regression check scenario
- [ ] Describes what WAS done, not what SHOULD be done
- [ ] "Not Addressed" items have both Reason (why not done) and Follow-up (action item)
- [ ] Searched Confluence for RCA page (`title ~ "{TICKET_KEY}"`), linked if found. If bug and no RCA: ran `create-rca` first
- [ ] If RCA exists: deviation from RCA noted honestly (if applicable)
- [ ] No estimation, no fix options, no new suggestions
- [ ] UAT Deployment section included — correct block selected (config-only | code-only | mixed), other two deleted
- [ ] ENV_SPECIFIC ID table populated in plain English (not tool syntax) — or table removed if all paths are STABLE
- [ ] For config/mixed: verify step is a plain app action, not a tool call reference
- [ ] For code/mixed: PR URL included
- [ ] Pre-post Output Guardian linter (Step 5a) ran — verdict captured (PASS / WARN with acknowledged rule IDs / SKIPPED with reason)
- [ ] No comment posted while linter verdict was FAIL

## Next step

After completing this skill, select EXACTLY ONE action from the decision tree below based on the ticket's current state (read `tickets/{TICKET_KEY}/session-log.md` and `rca.md` to determine). Print the block below with the chosen action substituted for `{ACTION_LINE}`. Substitute the actual ticket key for `{TICKET_KEY}`. Do NOT print the decision tree.

**Decision tree (reasoning input only):**

| State (read from `session-log.md` + RCA artifacts) | `{ACTION_LINE}` |
|---|---|
| Last apply was to `dev` | `/apply-fix {TICKET_KEY} uat` |
| Last apply was to `uat` | `/apply-fix {TICKET_KEY} prod` |
| Last apply was to `prod` and RCA has no Confluence URL | `/publish-rca {TICKET_KEY}` |
| All envs applied and RCA on Confluence | `Ticket is queued for QA — you're done` |

The next-step action is driven by env state, not by which template flavor you just posted. SHORT vs FULL is independent — a user could post either at any env stage and the next action stays the same.

**Block to print:**

```
---
**Next step**

{ACTION_LINE}
---
```
