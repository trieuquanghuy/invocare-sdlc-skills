---
name: prepare-uat
description: "Use when a teammate's Jira ticket (bug or story) points to a Confluence Technical Approach page via a comment and the user needs a UAT deploy file generated from it. Accepts either a bare ticket key OR a comment URL with focusedCommentId — with just a ticket key, scans the ticket's comments for Confluence links and asks which one is the handoff. Trigger on: prepare uat, build deploy from comment, build deploy from ticket, generate UAT deploy."
argument-hint: "Ticket key (e.g. GEN-2759) or comment URL with focusedCommentId"
disable-model-invocation: true
---

# Prepare UAT

Given a Jira comment URL (with `focusedCommentId`), follow the Confluence page linked in that comment, extract the **Technical Approach** and **Root Cause Analysis** (if present), and generate `tickets/{TICKET_KEY}/{TICKET_KEY}-deploy-uat.md` using [deploy-template.md](./references/deploy-template.md).

The fully-qualified filename (`{TICKET_KEY}-deploy-uat.md`) keeps the UAT plan distinct from a dev `deploy.md` in the same ticket folder.

This skill is **read-only against Jira and Confluence** and writes only to the local ticket folder. No Firebase writes.

## Overview

**Core principle: trust Confluence; never re-investigate.** The Technical Approach has already been authored by the BA / lead; this skill's job is to translate it into a deployer-ready file. Re-deriving the fix from code defeats the purpose and risks contradicting the reviewer.

**Output guardian:** apply `.claude/rules/output-guardian.md` — `{TICKET_KEY}-deploy-uat.md` is the shared artifact; no tool names, no session refs, no workspace paths in narrative.

**Firebase safety:** apply `.claude/rules/firebase-safety.md` — read-only. Every path the deploy file mentions MUST label its DB (RTDB or Firestore) explicitly; never guess. NEVER call write_rtdb / write_firestore.

**Secrets safety:** apply `.claude/rules/secrets-safety.md` — if any read returns a secret-looking value, redact before continuing; never write secrets into the deploy file or the Drive upload.

## Quick Reference

| Input | Output | Required |
|---|---|---|
| Jira ticket key OR comment URL with `focusedCommentId` | `tickets/{TICKET_KEY}/{TICKET_KEY}-deploy-uat.md` | yes |
| Confluence Technical Approach section | Write steps + What This Does table | yes |
| Confluence RCA section | Context comment at top of deploy file | optional |
| GitHub PR URL(s) for UAT (user-provided) | `## Code Dependencies` section in deploy file | only if Tech Approach references code |
| Local `document-templates/{Name}/` (twig + css) | Template Artifacts section with sha256 | only if Tech Approach references templates |
| Drive folder for template assets | Drive URLs in Template Artifacts table | opt-in (Step 6.5) |

Hand-off: review `{TICKET_KEY}-deploy-uat.md`, then `/apply-fix {TICKET_KEY} uat`.

## When to Use

- A teammate (BA / lead / dev) has already published the Technical Approach to Confluence and dropped the link as a Jira comment
- You need to produce a clean UAT deploy plan for the deployer without re-running investigation
- The user provides **either** a bare Jira ticket key (e.g. `GEN-2759`) **or** a Jira comment URL with `focusedCommentId`. When only a ticket key is given, this skill scans the ticket's comments for Confluence links and asks the user to pick the handoff comment.
- If the Confluence Technical Approach references code changes (e.g. file paths under `FCRM-Web/`, mentions of a PR, or merge / branch language), this skill asks the user for the PR URL(s) and adds a `## Code Dependencies` section to the deploy file.

## This is NOT

- A re-investigation — trust the Confluence page's Technical Approach. Do not re-derive it from the codebase.
- An RCA generator — if no RCA exists on Confluence, capture only the Technical Approach and note the absence in the deploy file.
- An apply-fix — this only writes the UAT deploy file. Hand off to `/apply-fix {TICKET_KEY} uat` for execution.
- A spec generator — this skips `spec.md`. Use `create-spec` if you need the full spec package.

---

## Step 1: Parse the Input

Accept **either** form:

- **Bare ticket key:** `GEN-2759`
- **Comment URL with focusedCommentId:** `https://invocarecompass.atlassian.net/browse/GEN-2759?focusedCommentId=327821234567`
- **Ticket URL without focusedCommentId:** `https://invocarecompass.atlassian.net/browse/GEN-2759` — treated as a bare ticket key

Extract:

- `TICKET_KEY` — **required**. If the input is just an ID (e.g. `GEN-2759`), that's it. If it's a URL, parse it from the `/browse/{TICKET_KEY}` path segment.
- `COMMENT_ID` — **optional**. Only present when the URL carries `?focusedCommentId=...`. Leave it empty otherwise.

If no `TICKET_KEY` can be extracted, stop and ask the user for the correct input.

---

## Step 2: Locate the Handoff Comment

Get the full Jira issue (with comments) via Atlassian MCP:

```
getJiraIssue(
  cloudId: "invocarecompass.atlassian.net",
  issueIdOrKey: "{TICKET_KEY}",
  fields: ["summary", "status", "issuetype", "comment"]
)
```

### Branch 2A — `COMMENT_ID` was provided

Locate the comment whose `id` matches `COMMENT_ID` exactly. **Do not fall back to the latest comment** if the ID does not match — stop and tell the user the comment ID was not found on the ticket.

### Branch 2B — Only a `TICKET_KEY` was provided (no `COMMENT_ID`)

1. Filter the ticket's comments down to those whose body contains at least one Confluence page URL — links of the form `https://invocarecompass.atlassian.net/wiki/spaces/.../pages/{PAGE_ID}/...`.
2. **Confluence-link comments only.** Do **not** fall back to the ticket description, linked subtasks, or any other source. If zero comments match, stop and ask the user to point you at the handoff (paste the comment URL or the Confluence URL directly).
3. Present every matching comment to the user — author, creation date, a short body preview (first ~150 chars), and the Confluence URL(s) it contains.
4. **Always confirm with the user, even when only one candidate exists.** Trusting Confluence means making the source explicit; one-match auto-pick risks silently following a stale or unrelated comment.
5. Capture the user's chosen comment as the handoff. Record its `id` as `COMMENT_ID` going forward.

### After either branch

From the chosen comment, capture:

- Comment author and creation date (for the provenance line in the deploy file)
- Comment body (markdown / ADF)
- **All Confluence URLs** in the body

If the chosen comment has **no Confluence link** in its body, stop and ask the user which page carries the Technical Approach.

If the chosen comment links to **multiple Confluence pages**, present the list and ask which one carries the Technical Approach.

---

## Step 3: Fetch the Confluence Page

For the chosen Confluence URL, extract the `pageId` from the path segment `/pages/{PAGE_ID}/`. Then:

```
getConfluencePage(
  cloudId: "invocarecompass.atlassian.net",
  pageId: "{PAGE_ID}"
)
```

From the page body, extract these sections (case-insensitive heading match — accept variants like "Technical Solution", "Proposed Approach", "Root Cause"):

| Section | Required | Used for |
|---------|----------|----------|
| **Technical Approach** | Yes | Drives the write steps and "What This Does" table |
| **Root Cause Analysis** | No | Captured as context comment block at the top of the deploy file |
| **Affected Paths / Changes** | Yes (or derivable from Technical Approach) | Each row → one Step block in the deploy file |
| **Verification** | No | Rolled into the Verification table |

If **Technical Approach** is missing, stop and tell the user which sections were and weren't found. Do not invent content.

---

## Step 3.5: Detect Code References and Capture PR URLs

Run **only when** the Confluence **Technical Approach** section references code changes. Skip otherwise — write `No code references found — skipping 3.5.` in your working notes and proceed to Step 4.

### How to detect

Scan the **Technical Approach** text for any of:

- Repo-relative paths to source files (e.g. `FCRM-Web/src/forms/FormController.ts`, `services/funeral-api/.../handler.go`, anything ending in `.ts`, `.tsx`, `.js`, `.jsx`, `.go`, `.py`, `.java`, `.cs`)
- GitHub PR URLs (`https://github.com/.../pull/{N}`)
- Explicit language: "PR", "pull request", "merge", "code change", "branch", "deploy build"

RCA and Verification sections are **not** in scope — code references in those sections do **not** trigger the PR ask.

### Capture PR URL(s)

Ask the user:

> The Technical Approach references code changes. Do you have a PR (or PRs) for UAT? Paste the GitHub URL(s), or reply `none` if there is no code PR for this fix.

Treat the user's response as authoritative — **do not scrape Jira's development panel, GitHub commits, or any other source** on your own.

If the user provides URL(s):

1. For each PR URL, optionally enrich via `gh pr view <url> --json number,state,baseRefName,headRefName,mergedAt,title,files`. If `gh` is unavailable or the call fails, capture only the URL and ask the user for the status (`merged` / `open` / `closed`).
2. Capture: PR URL, title, status, source branch, target branch, list of changed files (truncated to ~10 with a `+N more` suffix if needed).
3. The captured PR list goes into the deploy file's `## Code Dependencies` section (Step 5).

If the user replies `none`:

- Note that the Technical Approach mentions code but the user states there is no UAT PR.
- Still proceed — the `## Code Dependencies` section is added with a single line surfacing the mismatch, and the Step 7 summary repeats the note so the deployer is aware.

---

## Step 4: Classify Each Change

For every concrete change pulled from the Confluence page, classify:

1. **Database** — `RTDB` or `Firestore`. The Confluence page should state this. If ambiguous, query both and confirm where the path actually lives:
   ```
   query_rtdb(environment_name: "uat", path: "{PATH}")
   query_firestore(environment_name: "uat", path: "{PATH}")
   ```
   Pick whichever returns data. **Never guess** — using the wrong tool silently writes nothing or to the wrong system.
2. **Operation** — `create` / `update_partial` / `update_full` / `delete`. Default to `update_partial` when only specific fields change.
3. **Path stability** — note any segments that look env-specific (UUIDs, push IDs). For each, record the lookup query the deployer needs to run on UAT before substituting the ID.
4. **Current UAT state** — read the path on UAT now and paste the result. This becomes the "before" snapshot. **Read-only** — never write at this stage.

---

## Step 4.5: Detect and Resolve Template Artifacts

Run **only when** the Confluence Technical Approach references `document-templates/` (case-insensitive substring match on the Technical Approach section only — not RCA / Verification / other sections). Skip otherwise — write `No template artifacts referenced — skipping 4.5.` in your working notes and proceed to Step 5.

**Procedure:** [template-artifacts.md](./references/template-artifacts.md) — enumerate candidates (4.5a), verify local twig/css exist (4.5b), compute sha256 + size (4.5c), classify as new/update/mixed against the linked write op (4.5d), size-budget check (900 KB Firestore / 5 MB RTDB warn — 4.5e), capture Before-state integrity record for updates (4.5f), build the Template Artifacts table + full-sha256 block (4.5g).

**Output contract:** the `## Template Artifacts` section the saved deploy file carries (truncated 4+4 table for readability + full-64-char-hex fenced block below) — consumed by `apply-fix` Step 4b.0.

**Key invariants** (the reference enforces, but callers must know):
- De-duplicate by folder — one `T_id` per physical `document-templates/{Name}/` folder, even if cited multiple times.
- Firestore 900 KB budget is a HARD STOP (do not produce a deploy file); RTDB 5 MB is a WARN (user can override).
- Verbatim twig/css content NEVER goes into the saved deploy file — always sha256 + 10-line excerpt + size.
- Never guess on ambiguous mentions — ask the user.

---

## Step 5: Write the UAT Deploy File

Read [deploy-template.md](./references/deploy-template.md). Save the output to:

```
tickets/{TICKET_KEY}/{TICKET_KEY}-deploy-uat.md
```

Substitute the real ticket key into both placeholders (e.g. `tickets/GEN-2759/GEN-2759-deploy-uat.md`). Create the folder if missing. If a plain `deploy.md` already exists in the folder (from a dev workflow), leave it alone — the UAT file is a sibling, not a replacement.

Required adjustments to the template for this skill:

- **Header block** — add the following lines after the standard header:
  ```
  **Source:** Confluence — [Page Title]({CONFLUENCE_URL})
  **Origin Jira comment:** [{TICKET_KEY} comment]({JIRA_COMMENT_URL})
  **Target environment:** uat
  ```
  When Step 3.5 captured one or more PRs, add one more line:
  ```
  **Code PR:** [#1234]({PR_URL}) (merged — pre-apply check required)
  ```
  For multiple PRs, use `**Code PRs:** #1234, #1240, #1247 — see Code Dependencies section`.
- **What This Does table** — one row per write, with the `DB` column filled (`RTDB` / `Firestore`).
- **Code Dependencies section** — if Step 3.5 captured one or more PRs, expand the template's `## Code Dependencies` section into a PR table between the header block and `## What This Does`. Render as:

  > The Technical Approach for this fix includes code changes that must be merged and deployed to UAT before applying the config below.
  >
  > | PR | Title | Status | Branch | Files |
  > |----|-------|--------|--------|-------|
  > | [#1234]({PR_URL}) | Fix form validation | merged | feature/xyz → develop | `FCRM-Web/src/forms/FormController.ts`, +2 more |
  >
  > **Pre-apply check:** confirm the PR(s) above are merged and deployed to UAT before running `/apply-fix`.

  If Step 3.5 ran but the user replied `none` (code referenced but no PR), include the section with this single line: `The Technical Approach mentions code changes, but the source ticket reports no UAT PR. Deployer must confirm the code is in UAT another way before applying the config below.`

  If Step 3.5 was skipped entirely (no code references), omit this section.
- **Template Artifacts section** — if Step 4.5 ran, render the table built in 4.5g (and the full-sha256 block) as a new `## Template Artifacts` section between `## What This Does` and `## Environment-Specific IDs`. If Step 4.5 was skipped (no template references), omit this section entirely — do not add an empty placeholder.
- **Execution Steps** — replace the `{ENV}` placeholders with `uat` directly. This file is UAT-only.
- **ENV-specific paths** — annotate each affected step with `⚠️ ENV-SPECIFIC: resolve {SEGMENT} on UAT before writing` and place the lookup query inline above the write block.
- **Current UAT state** — under each write step, paste the pre-write query result inside a `Before:` block so the deployer can compare on rollback. **Exception for template fields** (per Step 4.5f): when a write changes a `template` and/or `styles` field, the `Before:` block carries the integrity record (sha256, size, 10-line excerpt) for those fields only — NOT the verbatim 45 KB string. Sibling fields in the same doc are pasted verbatim as usual.
- **Template injection in `data: {}` blocks** — when a write step is linked to a Template Artifact row (T1, T2, …) from Step 4.5g, do NOT inline the twig/css content into the `data: {}` block. Use the placeholder syntax `<ARTIFACT {T_id} twig>` and `<ARTIFACT {T_id} css>`. Example: `data: { label: "Memorial Slideshow Cover", template: <ARTIFACT T1 twig>, styles: <ARTIFACT T1 css>, active: true }`. The `<ARTIFACT …>` token is the contract apply-fix consumes — it reads the local file at write time, re-hashes against the Template Artifacts full-sha256 block, and substitutes the content into the actual Firebase write payload. **Never** paste the twig/css body into the deploy markdown — it bloats the file and makes diffs unreadable.
- **After-state record for update writes** — for every write classified as `update — *` in Step 4.5d, add an `After:` block under the write step, sibling to `Before:`. Its content for the changed template fields is the projected integrity record from Step 4.5c:
  ```
  After-template-sha256: <full 64-char sha256 of new local twig>
  After-template-excerpt: <first 10 non-blank lines of new local twig>
  After-template-size: <bytes>
  ```
  Same shape for `styles` if css changes. Apply-fix re-verifies these match the local file at write time. The `After:` block lets the deployer confirm rollback comparisons without round-tripping through the local repo.
- **Verification table** — fill from the Confluence page if a Verification section was found; otherwise build at minimum one read query per write to confirm the new value landed. For template-field writes, the `Expected:` column carries the After-sha256 (truncated to `a3f9…2c1b` for readability), so a post-deploy `query_rtdb`/`query_firestore` result can be hashed and compared without inlining 45 KB of expected text. Example expected cell: `sha256 of template field == a3f9…2c1b (T1 twig)`.
- **Quick Test** — 2–3 plain app actions (e.g. "Open the Funeral form, complete to Page 3, confirm export filename = `Death_Certificate.pdf`"). Never reference internal tools.
- **Rollback section — REQUIRED, never strip.** Retain the `## Rollback` section from the template and **expand Option B to be per-step** rather than the generic placeholder. The expanded section MUST contain:
  - **Option A — Session rollback (preferred):** keep the `rollback_session(session_id: "[FILLED BY APPLY-FIX]")` block. `apply-fix` fills the session ID after the run; `prepare-uat` leaves the placeholder.
  - **Option B — Per-step manual rollback** in **REVERSE order** of writes. For each write in the deploy file, render one numbered item:
    ```
    1. **Step {N} ({DB}, {PATH}):**
       ```
       write_{rtdb|firestore}(environment_name: "uat", path: "{PATH}", op: "{REVERSE_OP}", data: <Before snapshot from Step {N}>)
       ```
    ```
    Use `update_full` / `update_partial` / `delete` / `create` matching the inverse of the forward operation:
    - forward `create` → reverse `delete`
    - forward `delete` → reverse `create` with the captured `Before:` value
    - forward `update_*` → reverse `update_*` writing back the captured `Before:` value
    For template fields, write `data: <Before sha256: a3f9…2c1b — restore from local document-templates/{Name}/{Name}.twig at that hash>` (the deployer pulls the file from git history if the working tree no longer matches).
  - **No invented values** — every "restore to" value must trace back to a `Before:` block in this same deploy file. If a write has no captured `Before:` (e.g. a pure `create`), the reverse row reads `delete` with no payload.

Remove the `## IMPORTANT RULES` block and any unused template comments — the saved file must be clean and execution-ready. **The `## Rollback` section is NOT "unused template content" — it is required deliverable content. Never strip it.**

**Anti-patterns to avoid when writing this file:**
- Pasting the literal twig/css content into a `data: { template: "…45 KB of escaped twig…" }` block. → Always use `<ARTIFACT T_id twig>`.
- Pasting a 45 KB current twig value verbatim in a `Before:` block. → Capture sha256 + 10-line excerpt + size per Step 4.5f.
- Writing `template: <twig content>` or `template: <new twig content from document-templates/...>` as a half-instruction (the literal placeholder from the Confluence Technical Approach). The deploy file is a CONTRACT for apply-fix; placeholders without a Template Artifacts row are not actionable. If you see yourself about to write this, re-run Step 4.5 and define a `T_id` first.
- Omitting the Template Artifacts section because "the deployer can figure it out from the file paths." They can't — apply-fix needs the full sha256 to byte-match the local file before writing.

---

## Step 6: Output Guardian Pass

Re-read the file you just saved and strip anything that violates `.claude/rules/output-guardian.md`:
- No tool names (`firebase-explorer`, `mcp__...`, `getConfluencePage`, etc.) anywhere in the saved file
- No session IDs or run numbers
- No "AI investigated" / "Claude confirmed" / "queried via" phrasing
- No references to local workspace files — neither bare filenames (`rca.md`, `spec.md`, `session-log.md`, `rollback.md`), nor paths under `tickets/...`, `sessions/...`, `.claude/...`, nor relative links (`./...`, `../...`). Replace with inline prose ("the source Confluence page", "the session log"). Repo code paths like `FCRM-Web/src/forms/FormController.ts:42` are fine — the reader can find them on GitHub. **This rule is about not LINKING to a sibling file named `rollback.md`; it does NOT mean the `## Rollback` section in the deploy file should be stripped. Rollback content is required deliverable content (see Step 5).**
- The file must read as if the developer wrote it by hand from the Confluence page

The only allowed tool references are inside fenced `query_rtdb` / `query_firestore` / `write_rtdb` / `write_firestore` / `create_session` / `complete_session` blocks — those are deploy commands, not narration.

**Template-artifact specifics:**
- `document-templates/{Name}/{Name}.{twig,css}` paths in the Template Artifacts section ARE allowed — they reference real repo files (same exemption as `FCRM-Web/src/...` code paths).
- `<ARTIFACT T1 twig>` / `<ARTIFACT T1 css>` placeholders inside `data: {}` blocks ARE allowed — they are deploy syntax consumed by apply-fix, not narration. They never appear in prose outside a fenced write block.
- The saved deploy file MUST NOT contain the verbatim twig or css content anywhere — not in `data: {}` blocks, not in `Before:` blocks, not in `After:` blocks. If you see more than the 10-line excerpt per file referenced in Step 4.5f, the size-budget intent has been violated. Re-run Step 4.5 to extract the integrity record and re-render Step 5.

---

## Step 6.5: Drive Upload for Template Assets (opt-in, only if Step 4.5 ran)

Skip entirely when Step 4.5 was skipped (no template references). Otherwise, opt-in per run — never automatic.

**Procedure:** [drive-upload-template-assets.md](./references/drive-upload-template-assets.md) — cached-folder vs first-time-setup prompts (6.5.0), per-file collision detection with replace/keep-both/skip (6.5.ii), upload via `create_file` (6.5.iii), update the saved deploy file's Template Artifacts table with Drive URLs or skip/fail verdicts (6.5.iv), failure handling.

**Config key:** `template_assets_parent_folder_id` in `.claude/skills/_shared/config/drive.json` (NOT the `deploy_result_parent_folder_id` key used by `apply-fix` Step 4h). Writes preserve both keys. `drive.json` is created on first Drive-upload setup if it does not yet exist — an absent file is expected on a fresh checkout, not a dead reference.

**Key invariants:**
- The deploy file's Drive URL cells always carry an explicit verdict — never empty. Declined / failed / skipped each get a textual marker so the deployer knows whether to expect a Drive preview.
- A failure here never blocks the deploy — the local twig/css are the source of truth `apply-fix` consumes; the Drive mirror is for human review only.

---

## Step 6.6: Self-check the Quality Bar

Before handing off, walk every item in this skill's Quality Bar against the saved deploy file. For each item:

- If it passes, move on.
- If it fails AND the fix is mechanical (e.g. a DB column blank in the What This Does table, a missing Source/Origin header line, a stray `firebase-explorer` mention the Output Guardian pass missed), apply it now and re-read the file.
- If it fails AND requires fresh data or judgment (e.g. a path needs a UAT confirmation read, an ambiguous classification was glossed over), STOP and surface the gap to the user before continuing to Step 7.

This pass typically takes 30 seconds. There is no checker subagent for this skill — the deploy file is consumed downstream by `apply-fix`, and any structural defect (missing DB column, missing full-sha256 block, malformed `<ARTIFACT ...>` placeholder) becomes a `Step 4b.0` STOP that wastes a session-create cycle. Catching it here is the only QA gate.

Document any non-mechanical gaps you surfaced in the Step 7 summary so the deployer knows what to confirm before running `/apply-fix`.

---

## Step 7: Summarize

After saving, tell the user:
- File created: `tickets/{TICKET_KEY}/{TICKET_KEY}-deploy-uat.md`
- Source Confluence page (title + URL)
- **Handoff comment** — author, creation date, and a one-line summary. If Branch 2B (scan-and-confirm) was used, note that explicitly (e.g. `Scanned {N} comments, picked the {date} comment by {author}`).
- Number of writes per database (e.g. `3 RTDB writes, 1 Firestore write`)
- Whether RCA was found on the Confluence page (yes / no — affects whether `create-rca` is still needed locally)
- Any ENV-specific IDs the deployer must resolve before applying
- **Code Dependencies** (only if Step 3.5 ran):
  - If PR(s) were captured: list each PR URL + status + `Pre-apply check: confirm the PR(s) above are merged and deployed to UAT before running /apply-fix.`
  - If the user replied `none` despite code references: surface the mismatch — `Confluence Technical Approach references code, but the user reports no UAT PR — deployer should confirm code state out-of-band before /apply-fix.`
- **Template artifacts** (only if Step 4.5 ran): `{N} template artifacts captured ({M} new, {K} update — twig/css totals: …)`. List each `T_id` + Name + classification. If Step 6.5 ran a Drive upload, append `Drive mirror: {N} files uploaded, {K} skipped/declined — see Template Artifacts table for per-file URLs`. If Step 6.5 was declined, append `Drive mirror: skipped — user declined`.
- **Rollback** — confirm the deploy file includes the `## Rollback` section with Option A (session rollback) and Option B (per-step manual rollback in reverse order). Mention how many manual rollback steps were rendered (e.g. `Option B has 3 reverse-order rollback steps`).
- Next step: `Review {TICKET_KEY}-deploy-uat.md, then run /apply-fix {TICKET_KEY} uat` (add `--dry-run` first if you want to validate the plan without writes)

---

## Quality Bar

- [ ] Resolved `TICKET_KEY` and `COMMENT_ID` — directly from a comment URL, or by scanning the ticket's comments for Confluence links and confirming the handoff with the user
- [ ] Branch 2B path (ticket key only): scanned comments for Confluence links, presented every candidate to the user, and proceeded only after explicit confirmation — even when only one candidate existed
- [ ] No fallback to the ticket description, linked subtasks, or any non-comment source when the handoff comment couldn't be located
- [ ] Fetched the exact Jira comment by ID once `COMMENT_ID` was known — not the latest comment, not the description
- [ ] Located the Confluence page link(s) inside the comment and chose the correct one (asked the user if multiple)
- [ ] Fetched the Confluence page and extracted **Technical Approach** (required) and **Root Cause Analysis** (if present)
- [ ] Every path classified as `RTDB` or `Firestore` — confirmed via UAT read where the page was ambiguous
- [ ] Pre-write `Before:` snapshot pasted under each write step (template fields captured as sha256 + 10-line excerpt + size per Step 4.5f, never verbatim)
- [ ] ENV-specific path segments flagged with `⚠️` and a lookup query
- [ ] Output saved to `tickets/{TICKET_KEY}/{TICKET_KEY}-deploy-uat.md` — folder created if missing; any pre-existing `deploy.md` left untouched
- [ ] Header includes `Source` (Confluence URL) and `Origin Jira comment` lines
- [ ] No internal tool names, session IDs, AI/Claude references, or local-workspace file references (`rca.md`, `spec.md`, `session-log.md`, `tickets/...`, relative links) appear in the saved `{TICKET_KEY}-deploy-uat.md`
- [ ] No invented Firebase paths — every path traceable to the Confluence page or a UAT confirmation read
- [ ] No write was executed against Firebase — this skill is read-only on Firebase (Drive uploads in Step 6.5 are opt-in and explicitly approved by the user)
- [ ] Step 3.5 ran whenever the **Technical Approach** referenced code (file paths with code extensions, GitHub PR URLs, or merge/branch language)
- [ ] When code references were found: explicitly asked the user for the PR URL(s); did NOT scrape Jira's development panel or any other source
- [ ] PR metadata (URL, title, status, branch, files) captured via `gh pr view` where available, or via direct ask where it isn't
- [ ] `## Code Dependencies` section rendered in the saved deploy file when one or more PRs were captured (or when the user replied `none` despite code references); section omitted entirely when no code references were found
- [ ] Header carries `**Code PR:**` (or `**Code PRs:**`) line when one or more PRs were captured
- [ ] **`## Rollback` section is present in the saved deploy file** with Option A (session rollback) and **Option B expanded to per-step manual rollback in REVERSE order**. Every Option B step traces to a `Before:` block in the same deploy file — no invented restore values
- [ ] User offered the next step: `Review {TICKET_KEY}-deploy-uat.md, then /apply-fix {TICKET_KEY} uat`

**Template-artifact items** (skip when Step 4.5 was skipped — no template references on the Confluence page):

- [ ] Step 4.5 ran whenever the Technical Approach mentioned `document-templates/{Name}` (case-insensitive substring match)
- [ ] Every candidate template's local `.twig` and `.css` files were verified to exist; missing files surfaced and resolved before continuing (no silent assumptions)
- [ ] sha256 and byte size captured for every present file via `shasum -a 256`
- [ ] Each template classified as `new` / `update — twig only` / `update — css only` / `update — twig + css` / `update — full doc` / `delete`, derived from the linked write operation (no guessing)
- [ ] Firestore writes that would push the destination document over 900 KB were **stopped** with a clear message; no deploy file produced in that case
- [ ] RTDB writes over 5 MB warned; user explicitly approved before continuing; warning recorded under deploy file Notes
- [ ] For every `update — *` template: Before-{field}-sha256, Before-{field}-excerpt (10 non-blank lines), Before-{field}-size captured — verbatim 45 KB strings NEVER pasted into the deploy file
- [ ] Template Artifacts table rendered in the saved deploy file as `## Template Artifacts` (between `What This Does` and `Environment-Specific IDs`), with truncated sha256 for readability and a full-64-char sha256 block below the table for apply-fix to consume
- [ ] `data: {}` blocks for template writes use `<ARTIFACT {T_id} twig>` / `<ARTIFACT {T_id} css>` placeholders — the literal twig/css body NEVER appears in the saved deploy file
- [ ] `After:` integrity record (sha256 + excerpt + size) added under each update write — sibling to `Before:`
- [ ] Verification table's `Expected:` column for template writes carries the After-sha256 (truncated for readability)
- [ ] If user opted in to Step 6.5: each uploaded file's Drive URL is captured in the Template Artifacts table; declined/failed/skipped files have an explicit verdict cell (never empty)
- [ ] `drive.json` write (when first-time setup) merged the new `template_assets_parent_folder_id` without overwriting `deploy_result_parent_folder_id`
- [ ] Secrets Safety honored — no secret value read or written into the deploy file, the Drive upload payload, or any prompt; if any MCP call returned a secret-looking value, it was redacted before continuing

## Red Flags — STOP and reconsider

If you catch yourself thinking any of these while writing the deploy file, the next action is NOT what you were about to do. Pause and re-read the relevant Step.

**General (non-template):**

- "The latest Jira comment is the handoff — I'll fetch that instead of looking up the comment id." → **No.** When `COMMENT_ID` was provided (Branch 2A), locate the comment by that ID. Recency is not a signal — the handoff is the one the URL specifies.
- "Only one comment has a Confluence link — I'll skip the confirmation and just use it." → **No.** Branch 2B **always** confirms with the user, even on a single candidate. Trusting Confluence means making the source explicit; auto-picking risks silently following a stale or unrelated comment.
- "Multiple Confluence-link comments — the most recent is probably the right one." → **No.** Present every candidate; let the user pick. Recency is not authoritative.
- "No comment has a Confluence link, but the ticket description does — I'll use the description's link." → **No.** The skill is comment-based. The description may be stale, unrelated, or written before the fix was finalized. Ask the user where the handoff lives.
- "The Technical Approach references `FormController.ts` — I'll skim Jira's development panel for the PR." → **No.** Step 3.5 — ask the user. We chose explicit user-provided PR over Jira-dev-panel scraping for accuracy.
- "The user replied `none` but I can see a recent PR on the ticket in GitHub — I'll add it anyway." → **No.** The user's answer is authoritative. Surface the mismatch in the summary; do not silently override.
- "The deploy file already has the writes laid out; the deployer can figure out the rollback themselves — I'll strip the `## Rollback` section to keep the file clean." → **No.** The `## Rollback` section is required deliverable content. Strip it and the deployer loses their reverse-order playbook the moment session rollback isn't available.
- "Option B's per-step manual rollback is just Option A in slow motion; I'll leave it as the generic placeholder." → **No.** Option A depends on the session ID staying valid and the session-rollback path working. Option B is the cold-spare. Render every reverse-order step explicitly, tracing each restore value to a `Before:` block in this same file.
- "The path looks like a config — that's RTDB. I'll write the deploy plan against `write_rtdb`." → **No.** Step 4. Paths can look identical across RTDB and Firestore. Run both `query_rtdb` and `query_firestore` on UAT; use whichever returns data. Never guess.
- "The Technical Approach is thin — I'll re-investigate the fix from the codebase to fill the gaps." → **No.** Core principle: trust Confluence; never re-investigate. The Tech Approach is the contract — capture it as-is and note the gap. Re-investigation belongs in `/create-rca`, not here.
- "The Confluence page links to multiple pages; the first one looks like the right one." → **No.** Step 2. Ask the user which page carries the Technical Approach. The order of links is not authoritative.

**Template artifacts (re-open the Confluence page, re-run Step 4.5, re-render Step 5):**

- "The Technical Approach says the twig content goes here, I'll just paste it inline." → **No.** Step 4.5g defines a `T_id`; Step 5's `data: {}` uses `<ARTIFACT {T_id} twig>`. The deploy file never carries the full twig body.
- "Apply-fix will read the local file when it runs, so I can leave `template: <twig content>` as a literal placeholder." → **No.** The deploy file IS the contract. Without a Template Artifacts row + full-sha256 block, apply-fix has no integrity hash to verify, no Drive URL to report, and no classification (new vs update).
- "The css is unchanged for this update, so I'll skip the Template Artifacts row entirely." → **No.** Even an `update — twig only` row carries the `T_id` and the twig file's sha256. The css column reads `(unchanged)`. Skipping the row hides the new content's integrity hash from apply-fix.
- "The 45 KB Before snapshot is just text — pasting it makes the diff complete." → **No.** Step 4.5f captures sha256 + 10-line excerpt + size for any template field that's about to change. Verbatim strings >8 KB never go into the deploy file.
- "The Firestore document is currently 700 KB; adding a 250 KB twig will be fine." → **No.** Step 4.5e's budget includes the existing fields plus the projected payload. If the projected total exceeds 900 KB, stop — the pattern needs a Drive-id reference, not inline content. Confirm the storage shape with the BA before re-running.
- "The Confluence Technical Approach is silent on whether the css is part of the change — I'll assume it is, since the folder has both files." → **No.** Step 4.5d derives classification from the operation, not from disk contents. If the page is ambiguous, ask the user.
- "Step 6.5 (Drive upload) failed; I'll retry it silently." → **No.** Surface the error verbatim. The user re-runs the upload manually. Apply-fix can still proceed because the local files are the source of truth.

---

## Common Mistakes

| Mistake | What to do instead |
|---|---|
| Re-investigating the fix from the codebase because the Confluence page seems thin. | The Technical Approach is the contract — capture it as-is and note any gap. Re-investigation belongs in `/create-rca`, not here. |
| Fetching the latest Jira comment instead of the one whose `id` matches `COMMENT_ID`. | Step 2 — locate the comment by ID. The latest comment may be a discussion reply, not the Confluence handoff. |
| Guessing `RTDB` vs `Firestore` from path shape because the Confluence page is ambiguous. | Step 4 — `query_rtdb` AND `query_firestore` on UAT, use whichever returns data. Never guess. |
| Pasting a 45 KB twig body verbatim into a `data: {}` block. | Use `<ARTIFACT T_id twig>` (Step 4.5g + Step 5). The deploy file carries integrity hashes, never raw template bodies. |
| Skipping the `Before:` snapshot under a write step because "the deployer can read it themselves". | Step 5 — the `Before:` block is the rollback baseline. For template fields use the sha256+excerpt+size record (Step 4.5f). |
| Telling the user to promote via a separate migration step. | `/apply-fix` is the canonical apply path (post-2026-05-16). Hand off `Review {TICKET_KEY}-deploy-uat.md, then run /apply-fix {TICKET_KEY} uat`. |
| Leaving `Drive mirror:` cells in the Template Artifacts table empty when Step 6.5 was declined. | Always carry an explicit verdict: `skipped — user declined`, `failed: <reason>`, or the Drive URL. Empty cells leave the deployer guessing. |
| Stopping with "URL required" when the user provided only a ticket key. | Branch 2B — scan the ticket's comments for Confluence links and ask the user to pick the handoff. Stop only when zero comments match. |
| Auto-picking the single Confluence-link comment without asking. | Always confirm. Trusting Confluence means making the source explicit, even on a one-match case. |
| Falling back to the ticket description's Confluence link when no comment has one. | Step 2 — comments only. Ask the user where the handoff lives; do not pull from the description, linked subtasks, or any other source. |
| Scraping Jira's development panel to find the PR for UAT. | Step 3.5 — ask the user. We chose explicit ask over dev-panel scraping because PRs in that panel are sometimes stale or unrelated to the fix. |
| Adding a `## Code Dependencies` section when the Tech Approach did not reference code. | Skip Step 3.5 entirely when no code references are detected. Omit the section. The default deploy file is config-only. |
| Stripping the `## Rollback` section because the saved file should be "clean". | The `## Rollback` section is required deliverable content (Step 5). Strip the `## IMPORTANT RULES` block and unused template *comments*; never the rollback section. |
| Leaving Option B in the `## Rollback` section as the generic "for each write above, restore the Before value" placeholder. | Render Option B per-step in REVERSE order. Each step names the path, DB, reverse op, and the captured `Before:` value the deployer writes back. |
