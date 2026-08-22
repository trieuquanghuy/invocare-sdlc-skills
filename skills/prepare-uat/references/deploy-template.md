## IMPORTANT RULES (remove this section before saving):
- This template is consumed by `prepare-uat` to produce a UAT-only deploy plan.
- Every write step must have `DB` filled (`RTDB` or `Firestore`) — never guess; confirm via a UAT read.
- Every `ENV_SPECIFIC` path segment must have a `⚠️ ENV-SPECIFIC: resolve …` line above the write block and an inline lookup query.
- Each write step must include a `Before:` snapshot captured from UAT immediately before saving the file. **For template fields** (`template` / `styles` on a `document-templates/...` write): the `Before:` block carries `sha256 + 10-line excerpt + size` per Step 4.5f — NEVER the verbatim string. Sibling fields stay verbatim.
- **Template Artifacts section** is mandatory whenever Step 4.5 ran. Render it between `## What This Does` and `## Environment-Specific IDs`. Omit entirely when no template was referenced.
- Write `data: {}` blocks use `<ARTIFACT {T_id} twig>` and `<ARTIFACT {T_id} css>` placeholders for template fields — the literal twig/css body NEVER appears in the saved deploy file. `apply-fix` substitutes the placeholders at write time after re-hashing the local file.
- Update writes get a one-line `After:` reference (`After: matches T{id} (twig sha256 {first8}…{last4}, {size} KB)`) sibling to `Before:` — the full integrity record lives only in the Template Artifacts block.
- Output Guardian (`.claude/rules/output-guardian.md`) applies to the SAVED file: no internal tool names in prose, no session IDs, no AI/Claude references, no references to other workspace files (`rca.md`, `spec.md`, `session-log.md`, `running-log.md`, `tickets/...`, `./...`). Tool references are only allowed inside fenced query/write blocks — those are deploy syntax, not narration. `document-templates/{Name}/...` repo paths in the Template Artifacts section ARE allowed (same exemption as `FCRM-Web/src/...`). `<ARTIFACT T_id ...>` placeholders inside fenced write blocks ARE allowed (deploy syntax).
- Author identity is the developer who prepared the deploy — never hardcode a person's name and never imply AI involvement.
- Remove this IMPORTANT RULES block before saving.

---

# [TICKET_KEY]: UAT Deploy Plan

**Ticket:** [[TICKET_KEY]]([JIRA_URL]/browse/[TICKET_KEY]) — [JIRA_TITLE]
**Source:** Confluence — [[Page Title]([CONFLUENCE_URL])
**Origin Jira comment:** [[TICKET_KEY] comment]([JIRA_COMMENT_URL])
**Target environment:** `uat`
**Fix type:** config | mixed
**Prepared by:** [developer name]

[Optional 1–2 sentences from the Confluence Root Cause Analysis, if present. If absent, write `Root Cause Analysis not captured on the source page.`]

---

## What This Does

| # | Change | DB | Path or file | Operation | Notes |
|---|--------|-----|--------------|-----------|-------|
| 1 | [short description] | RTDB / Firestore | `[path or file]` | create / update_partial / update_full / delete | [shared path / caveats if any] |

---

## Template Artifacts

> Include this section ONLY when one or more writes consume a `document-templates/{Name}/...` source (Step 4.5 ran). Omit entirely otherwise.
>
> Truncated sha256 (`a3f9…2c1b`) is for human readability. The FULL 64-char sha256 block below is what `apply-fix` byte-matches against the local file at write time.

| ID | Name | Files | Class | twig sha256 | css sha256 | New size | Linked write | Size budget | twig Drive URL | css Drive URL |
|----|------|-------|-------|-------------|------------|----------|--------------|-------------|----------------|---------------|
| T1 | [Template Name] | twig + css | new / update — twig only / update — css only / update — twig + css / update — full doc / delete | `a3f9…2c1b` | `8e44…91d2` | [N KB] | Step 2.[i] (RTDB / Firestore [op]) | RTDB ok / RTDB warn (5 MB+) / Firestore ok / [stop reason] | https://drive.google.com/file/d/{id} / skipped — user declined / failed: <reason> / skipped — duplicate ambiguity | (same options) |

**Full sha256 block** (apply-fix consumes this, not the truncated table):

```
T1.twig.sha256: [full 64-char hex digest of local document-templates/{Name}/{Name}.twig]
T1.css.sha256:  [full 64-char hex digest of local document-templates/{Name}/{Name}.css — or `(unchanged)` for update — twig only / `(none)` if the template has no css]
```

[Repeat one row per template artifact. The full sha256 block carries one line per file that has a hash; lines for unchanged or absent files use the placeholder verbs above.]

---

## Code Dependencies

> Include this section ONLY when the Confluence Technical Approach calls for code changes alongside config writes (`prepare-uat` Step 3.5 ran). Omit entirely for pure-config plans.
>
> The deployer must confirm every PR below is merged and deployed to UAT before any write in `## Execution Steps` runs.

The Technical Approach for this fix includes code changes that must be merged and deployed to UAT before applying the config below.

| PR | Title | Status |
|----|-------|--------|
| [#1234]([PR_URL]) | [PR title from `gh pr view`] | merged / open / closed |

**Pre-apply check:** confirm the PR(s) above are merged and deployed to UAT before running `/apply-fix`.

> **Code-referenced-but-no-PR variant:** if Step 3.5 detected code references but the user replied `none`, drop the table entirely and render this single line in its place: `The Technical Approach mentions code changes, but the source ticket reports no UAT PR. Deployer must confirm the code is in UAT another way before applying the config below.`

---

## Environment-Specific IDs

> If every path in the table above is stable across environments, write `n/a — all paths are stable.` and remove the lookups below.

### Lookup: [SEGMENT_NAME]

```
query_rtdb(
  environment_name: "uat",
  path: "[parent_path]"
)
```

Find the record where `[field]` == `"[exact value carried over from the Confluence page]"`.
Use that key as `[SEGMENT_NAME]` in the matching write step below.

[Repeat one Lookup block per env-specific segment.]

---

## Execution Steps

### Step 1 — Create session

```
create_session(
  environment_name: "uat",
  description: "[TICKET_KEY]: [short description]"
)
```

Save the returned `session_id` — required for every write below and for rollback.

---

### Step 2.[i] — [Change description] — [RTDB | Firestore]

> ⚠️ ENV-SPECIFIC: resolve `[SEGMENT_NAME]` using the lookup above before executing. [Remove this line if the path is stable.]
>
> [If this write is linked to a Template Artifact (T1, T2, …) from the table above, add:]
> 🧩 TEMPLATE ARTIFACT: T[id] — apply-fix substitutes `<ARTIFACT T[id] {twig|css}>` placeholders below with the local file content after byte-matching the full sha256 from the Template Artifacts block.

**Before:** (captured from UAT during preparation)

```[json | text]
[Paste the exact pre-write value here.

 CASE 1 — Path exists on UAT (any update_*  / delete write):
   Paste the verbatim pre-write value.

   Exception for template-artifact writes: for `template` / `styles` fields, paste an integrity record instead of the verbatim string:

   Before-template-sha256: [full 64-char hex of the CURRENT Firebase `template` value]
   Before-template-excerpt:
     [first 10 non-blank lines of the current Firebase `template`]
   Before-template-size: [bytes]

   Before-styles-sha256: [full 64-char hex of the CURRENT Firebase `styles` value, or `(unchanged)` if css isn't part of this update]
   Before-styles-excerpt:
     [first 10 non-blank lines, or `(unchanged)`]
   Before-styles-size: [bytes, or `(unchanged)`]

   Sibling fields in the same doc are pasted verbatim as usual.

 CASE 2 — Path does NOT exist on UAT (`create` write):
   Write a single line: `path does not exist on UAT — fresh create`. No Before-{field}-sha256 capture for any field (there's nothing to hash). The Template Artifacts full-sha256 block above carries the integrity hash for the new content; `apply-fix` re-hashes the local file at write time against that record.]
```

[If the operation is `update_partial` / `update_full` on a template-artifact write, add a one-line After reference sibling to Before — the full integrity record (64-char sha256 + 10-line excerpt + size) lives ONLY in the Template Artifacts block above:]

**After:** matches T[id] (twig sha256 [first8]…[last4], [N] KB[; css sha256 [first8]…[last4], [N] KB if css changes — or omit]).
Apply-fix re-verifies the local file against the Template Artifacts full-sha256 block before writing.

**Write:**

```
write_rtdb(  // OR write_firestore — match the DB column above
  environment_name: "uat",
  session_id: "<SID>",
  allow_writes: true,
  path: "[EXACT_PATH]",
  operation: "[create | update_partial | update_full | delete]",
  data: {
    [exact field]: [exact value]
    // For template-artifact writes, use placeholder syntax for template/styles fields:
    // template: <ARTIFACT T[id] twig>,
    // styles:   <ARTIFACT T[id] css>,
    // Other fields stay literal:
    // label: "Memorial Slideshow Cover",
    // kind:  "slideshow",
    // active: true
  }
)
```

Why: [one sentence on what this achieves, in plain language.]

[Repeat the Step 2.[i] block for every write in the plan.]

---

### Step [last] — Complete session

```
complete_session(session_id: "<SID>")
```

---

## Verification

> One row per check. Build at minimum one read per write to confirm the new value landed. If the Confluence page already lists verification queries, use those.

| # | Check | DB | Command | Expected |
|---|-------|-----|---------|----------|
| V1 | [check name] | RTDB / Firestore | `query_rtdb(environment_name: "uat", path: "[path]")` | [expected outcome — for template fields use `sha256 of {field} == a3f9…2c1b (T[id] {twig\|css})` to avoid pasting 45 KB of expected text; deployer hashes the read result] |
| V2 | [check name] | RTDB / Firestore | `[command]` | [expected outcome] |

---

## Quick Test

> Plain app actions a tester can run after the deploy. Never reference internal tools.

- [ ] [Step 1 — app action and expected outcome]
- [ ] [Step 2 — app action and expected outcome]
- [ ] [Step 3 — regression check on an adjacent flow]

---

## Rollback

> Required section — never strip. Option A is the fast path; Option B is the cold-spare the deployer falls back to when session rollback is unavailable.

**Option A — Session rollback (preferred):**

```
rollback_session(session_id: "[FILLED BY APPLY-FIX AFTER THE RUN]")
```

This restores every path written in this plan to its `Before:` value in a single atomic operation. `apply-fix` writes the real `session_id` into this block after a successful run.

**Option B — Per-step manual rollback** (fallback when the session ID is unavailable or `rollback_session` fails):

Execute in **REVERSE order** of the forward writes above. Each step below names the path, the DB, the reverse op, and the captured `Before:` value the deployer writes back.

Render one numbered item per forward write. Forward op → reverse op mapping:

| Forward | Reverse | Notes |
|---------|---------|-------|
| `create` | `delete` | No payload required. |
| `delete` | `create` | Use the captured `Before:` value as the payload. |
| `update_partial` | `update_partial` | Restore only the fields that were touched, using `Before:`. |
| `update_full` | `update_full` | Restore the entire document/path from `Before:`. |

For **template fields** (`template` / `styles`), the `Before:` block stores a `sha256 + 10-line excerpt + size` integrity record per Step 4.5f. The reverse write reads `data: <Before sha256: a3f9…2c1b — restore from local document-templates/{Name}/{Name}.twig at that hash>`. The deployer pulls the file from git history if the working tree no longer matches the recorded hash.

Example shape (substitute real values from this deploy file's write steps):

```
1. **Step [N] ([RTDB | Firestore], [PATH]):**
   ```
   [write_rtdb | write_firestore](environment_name: "uat", path: "[PATH]", op: "[REVERSE_OP]", data: [Before value from Step N's Before: block])
   ```

2. **Step [N-1] (...):**
   ...
```

**Provenance:** every "restore to" value above traces back to a `Before:` block in this same file. No invented values.
