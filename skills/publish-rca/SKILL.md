---
name: publish-rca
description: "Use when publishing a completed RCA to Confluence for the first time, or refreshing an already-published page after edits. Triggers on: publish rca, post rca, update rca page, sync rca to confluence, upload rca, refresh rca on confluence."
argument-hint: "Jira ticket key (e.g. GEN-1952)"
disable-model-invocation: true
---

# Publish RCA to Confluence

Publish or update the local `rca.md` to Confluence under **Team 2 - Bugbucket**.
Updates existing page if found (preserves URL), creates new page if not.

**Output guardian:** all output reads as written by a developer. Apply `.claude/rules/output-guardian.md` — never include tool names, session IDs, or any indication of automation.

## NOT This Skill If

- User wants to draft a new RCA or refresh its content → use `/create-rca`.
- User wants to post a Jira comment summarising what was done → use `/ticket-comment`.
- User wants to publish anything other than `rca.md` to Confluence (e.g. a spec, a runbook) → handle manually; this skill is RCA-specific.

---

## Title Format

```
RCA: {TICKET_KEY} - {Feature Name} - {Topic}
```

| Part | Source | Example |
|------|--------|---------|
| `RCA:` | Fixed prefix | `RCA:` |
| `{TICKET_KEY}` | Ticket key | `GEN-1952` |
| `{Feature Name}` | "Where to Work" section or ticket summary — main component | `Email Templates` |
| `{Topic}` | Specific aspect investigated — root cause area, 1–3 words | `Channels` |

Full example: `RCA: GEN-1952 - Email Templates - Channels`

## Prerequisite

`tickets/{TICKET_KEY}/rca.md` must exist. If not, run `create-rca` first.

---

## Step 1: Read and Derive Title

Read `tickets/{TICKET_KEY}/rca.md` in full. Extract:
- **Feature Name** — from Section 7.1 "Repositories Involved" (primary repo) or the ticket Summary line at the top
- **Topic** — from the root cause classification area or specific symptom (1–3 words)

Propose the title to the user:

```
Proposed title: "RCA: {TICKET_KEY} - {Feature Name} - {Topic}"

Publish with this title? (yes / edit)
```

Wait for confirmation. If user edits, use their title exactly.

---

## Step 2: Find Existing Page

> **`cloudId` note:** the `cloudId` is the site's UUID, resolved **once** per invocation via `getAccessibleAtlassianResources` (match the resource whose `url` is `https://invocarecompass.atlassian.net`) and reused for every Confluence call below. The `invocarecompass.atlassian.net` value shown in the calls is the site host for reference — substitute the resolved UUID. Do not treat the host-vs-UUID difference as a bug.

Search Confluence for an existing RCA for this ticket:

```
searchConfluenceUsingCql(
  cloudId: "invocarecompass.atlassian.net",
  cql: "title ~ \"RCA: {TICKET_KEY}\" AND type = page",
  limit: 5
)
```

---

## Step 2b: Compare — Outdated or In Sync?

**If page found:** fetch its full content:
```
getConfluencePage(
  cloudId: "invocarecompass.atlassian.net",
  pageId: "{EXISTING_PAGE_ID}"
)
```

Compare the Confluence content against local `rca.md` across these key sections:

| Section | What to compare |
|---------|----------------|
| Executive Summary | Root cause summary — classification + explanation |
| Recommendations | Fix list — any additions, removals, or changes |
| Technical Analysis | Primary repo and fix point (Section 7) |
| Evidence Summary | Key Firebase paths or code references (Section 3.4) |

**Decision:**

| Result | Action |
|--------|--------|
| **All sections match** | Report "✓ Confluence RCA is already in sync with local rca.md — no update needed." Stop here. |
| **Sections differ** | Show a concise diff summary (what changed), then ask: "Confluence RCA is outdated. Update it? (yes / no)" |
| **No page found** | Proceed to create (Step 3) |

**Diff summary format:**
```
Confluence RCA is outdated for {TICKET_KEY}:

~ Root Cause: classification changed from [X] to [Y]
+ Recommended Solutions: 2 new fixes added
~ Where to Work: primary repo changed

Update Confluence with the latest local version? (yes / no)
```

Only proceed to Step 3 if the user confirms yes.

---

## Step 2c: Pre-publish Output Guardian linter

Before calling `createConfluencePage` or `updateConfluencePage`, gate the rca.md body through the linter subagent.

1. Read the shared linter prompt: `.claude/skills/_shared/contracts/output-guardian-linter.md`.
2. Dispatch a `pipeline-checker` subagent (`.claude/agents/pipeline-checker.md`) with:
   - The full prompt from the shared linter
   - `host: "confluence-page"`
   - `ticket_key`: the current ticket key
   - `body`: the full content of `tickets/{TICKET_KEY}/rca.md`
3. Parse the JSON result block per `.claude/skills/_shared/contracts/checker-contract.md`: `{ verdict, host, ticket_key, summary, iteration_hint, gaps[] }`.
4. Branch on verdict:
   - **FAIL** → print every blocker gap with its body:line evidence. Refuse to publish. Print: `RCA NOT published — Output Guardian linter detected blockers. Fix tickets/{TICKET_KEY}/rca.md and re-run /publish-rca {TICKET_KEY}.` Exit.
   - **WARN** → print every warning gap. Ask `Proceed anyway? (yes/no)`. If `no` → exit. If `yes` → continue.
   - **PASS** → continue silently.

If the checker dispatch fails or returns malformed JSON: print `Output Guardian linter could not run: <reason>.` Then ask `Proceed without the linter? (yes/no)`. Capture the linter status in the Step 5 summary as `Linter: SKIPPED (dispatch failure: <reason>)`.

If `pipeline-checker` is unavailable on this platform and you fall back to a `general-purpose` subagent (per `agents-safety.md` A2), surface it to the user: `pipeline-checker not available, falling back to general-purpose with prompt-level read-only guard`.

This linter runs ONCE per `/publish-rca` invocation — it does not iterate.

---

## Step 3: Create or Update

### No existing page → Create new

Parent page is hardcoded — no search needed:
- **Parent:** Team 2 - Bug Bucket
- **Parent ID:** `327231504407`
- **Space:** `KMS2`
- **Cloud:** `invocarecompass.atlassian.net`

```
createConfluencePage(
  cloudId: "invocarecompass.atlassian.net",
  spaceKey: "KMS2",
  parentId: "327231504407",
  title: "RCA: {TICKET_KEY} - {Feature Name} - {Topic}",
  content: "{rca.md content}"
)
```

### Existing page found and outdated → Update

Update preserves the page URL so existing Jira links keep working:
```
updateConfluencePage(
  cloudId: "invocarecompass.atlassian.net",
  pageId: "{EXISTING_PAGE_ID}",
  title: "RCA: {TICKET_KEY} - {Feature Name} - {Topic}",
  content: "{rca.md content}",
  version: {current_version + 1}
)
```

> **Why update instead of delete+create:** No delete tool available in Confluence MCP. Update is safer anyway — it preserves the page URL, so any Jira links or bookmarks continue to work.

---

## Step 4: Save URL Locally

After publish succeeds, replace the placeholder line in `tickets/{TICKET_KEY}/rca.md`:

Find: `**Confluence RCA:** <!-- publish-rca writes URL here -->`

Replace with:
```markdown
**Confluence RCA:** [RCA: {TICKET_KEY} - {Feature Name} - {Topic}]({confluence_page_url})
```

This lets `ticket-comment` find the URL in rca.md without re-searching Confluence.

---

## Step 5: Summarize

Tell the user:
- Action: **created** or **updated**
- Confluence URL (clickable)
- Title used
- Next step: `Run /ticket-comment {TICKET_KEY} to post the Jira comment with RCA link`

---

## Quality Bar

- [ ] Title follows format: `RCA: {TICKET_KEY} - {Feature Name} - {Topic}`
- [ ] User confirmed title before publishing
- [ ] Searched for existing page before creating new one
- [ ] User confirmed when updating an existing page
- [ ] Confluence URL prepended to `tickets/{TICKET_KEY}/rca.md`
- [ ] Space key `KMS2` and parent ID `327231504407` used — do not change these
- [ ] Pre-publish Output Guardian linter (Step 2c) ran — verdict captured (PASS / WARN with acknowledged rule IDs / SKIPPED with reason)
- [ ] No page created or updated while linter verdict was FAIL

## Next step

After completing this skill, print this block to the user before ending. Substitute the actual ticket key for `{TICKET_KEY}` if known; otherwise leave the placeholder.

```
---
**Next step**

The RCA is published. Ticket is done unless QA reports issues.

Related:
- /task-status {TICKET_KEY} — confirm Jira state
---
```
