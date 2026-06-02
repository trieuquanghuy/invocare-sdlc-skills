# Template Artifact Capture (prepare-uat Step 4.5)

Capture twig/css template artifacts by reference + integrity hash, not by inlining their content into the saved deploy file.

**Called by:** `prepare-uat` SKILL.md, between Step 4 (classify changes) and Step 5 (write the deploy file).

**Trigger:** run **only when** the Confluence Technical Approach references `document-templates/` (case-insensitive substring match on the Technical Approach section only — NOT the RCA, Affected Paths, Verification, or other narrative sections). Skip for every other ticket — write `No template artifacts referenced — skipping 4.5.` in your working notes and proceed to Step 5.

**Wire-format contract:** [`_shared/references/template-artifact-protocol.md`](../../_shared/references/template-artifact-protocol.md) — defines `T_id` naming, the truncated table format, the full-sha256 block format, the classification taxonomy, the `<ARTIFACT T_id ...>` placeholder syntax, and the Before/After integrity record format. This file is the **producer** side; everything documented in the protocol is what this skill must emit.

**Why this step exists:** twig/css bodies are 12-45 KB. Inlining them into the saved deploy file bloats it, breaks diffs, and risks exceeding Firestore's 1 MiB document cap. This step writes the bodies into Firebase **by reference**, captured as sha256 + size + 10-line excerpt.

---

## Step 4.5a — Enumerate candidate template folders

Scan **only the Technical Approach section** of the Confluence page for every `document-templates/{Name}` mention. References in the RCA, Affected Paths, Verification, or any other section are narrative context — they describe history, prior tickets, or check criteria, not new writes. Do NOT enumerate them as candidates. Build a candidate list. For each candidate:

```
Candidate: "{Name}"
  twig: document-templates/{Name}/{Name}.twig
  css : document-templates/{Name}/{Name}.css
```

**De-duplicate by folder** per the protocol's `T_id` rule — register ONE `T_id` per physical folder, even if cited multiple times in the Technical Approach. Note multiple mentions in your working notes; never produce two artifacts for one folder.

If a mention is ambiguous (e.g. the page says `document-templates/` without a specific subfolder, or names a template loosely like "the new slideshow template"), stop and ask the user. **Never guess.**

## Step 4.5b — Verify local files exist

For each candidate, check that BOTH files exist under `document-templates/{Name}/`:

| Situation | Behaviour |
|---|---|
| Both `.twig` and `.css` present | Proceed. |
| Only `.twig` (no `.css`) — and the Technical Approach explicitly says the template has no separate stylesheet | Proceed; record `css: none`. |
| Only `.twig` (no `.css`) — Technical Approach is silent on css | Stop and ask: `Template "{Name}" has a .twig but no matching .css under document-templates/{Name}/. The Confluence page does not say if styles are intentional. Continue without css? (yes / no)`. |
| Only `.css` (no `.twig`) | Stop unconditionally. Report `Template "{Name}" has a .css but no .twig — cannot proceed without the template body. Confirm the source on Confluence.` and exit Step 4.5. |
| Neither file present | Stop. Report `Template "{Name}" referenced in Confluence but document-templates/{Name}/ does not exist in the local repo. Sync the repo or correct the name before re-running.` |

## Step 4.5c — Compute sha256 and byte size

For each candidate that survived 4.5b, capture for every file present:

```
sha256: <hex digest>
size:   <bytes, formatted as KB / MB>
```

Use `shasum -a 256 {path}` (or equivalent). The full 64-char hex digest is the authoritative integrity hash the protocol's full-sha256 block carries. Truncate to 4+4 characters only for the readable table.

## Step 4.5d — Classify each template

Look up the artifact's linked write operation in Step 4 and select a classification per the protocol's [classification taxonomy](../../_shared/references/template-artifact-protocol.md#classification-taxonomy). If the operation can't be derived from the Technical Approach, stop and ask the user.

## Step 4.5e — Size-budget check (mandatory)

For every write that injects a template artifact, compute the projected payload size and verify it fits the target DB:

| DB | Rule | Action on breach |
|---|---|---|
| **Firestore** | A single document is hard-capped at **1 MiB** (1,048,576 bytes) by Firestore itself. If `size(twig) + size(css) + size(other_fields_in_data_block) > 900_000` bytes (≈900 KB — leaves ~150 KB safety margin for field-name overhead and JSON encoding) | **Stop.** Tell the user: `Template "{Name}" would push the Firestore document at {path} to ~{N} KB — over the 900 KB safety budget (Firestore caps documents at 1 MiB). This pattern needs a Drive-id reference, not inline content. Confirm the storage shape with the BA on Confluence before re-running.` Do not produce a deploy file. |
| **RTDB** | RTDB has no per-node 1 MiB cap, but a single string node above ~5 MB is a smell (slow reads, expensive sync). If `size(twig) + size(css) > 5_000_000` bytes (5 MB) | **Warn.** Tell the user: `Template "{Name}" totals {N} MB — large for an RTDB string node. Continue? (yes / no)`. On `no`, stop. On `yes`, record the warning verbatim under the deploy file's Notes section. |

For deletes, skip the size check (no payload is being injected).

The size budget verdict (`RTDB ok` / `Firestore ok` / `RTDB warn — N MB`) appears in the truncated table's `Size budget` column.

## Step 4.5f — Before-state capture for updates (read-only)

For every template classified as `update — *`, you already have the Firebase document's pre-write value from Step 4 (Step 4.4 "Current UAT state"). Derive the integrity record per the protocol's [Before / After integrity record format](../../_shared/references/template-artifact-protocol.md#before--after-integrity-records-for-update---writes):

```
Before-template-sha256: <full 64-char hex of current Firebase template field>   (only if twig is being changed)
Before-template-excerpt: <first 10 non-blank lines of current Firebase template>
Before-template-size: <bytes>
Before-styles-sha256: <full 64-char hex of current Firebase styles field>       (only if css is being changed)
Before-styles-excerpt: <first 10 non-blank lines>
Before-styles-size: <bytes>
```

Apply-fix re-reads these fields on UAT and re-computes the sha256 immediately before the write; if Firebase hash differs from `Before-*-sha256`, that's drift since you prepared the plan, and apply-fix surfaces it for explicit acknowledgement. Without this capture the drift check is impossible.

Verbatim 45 KB strings NEVER go into the deploy file — only the integrity record.

## Step 4.5g — Build the Template Artifacts table and full-sha256 block

Render the data per the protocol's [truncated table format](../../_shared/references/template-artifact-protocol.md#truncated-table-format) and [full-sha256 block](../../_shared/references/template-artifact-protocol.md#full-sha256-block) — both are mandatory.

Step 5 of the parent skill places the rendered section under `## Template Artifacts` between `## What This Does` and `## Environment-Specific IDs` in the saved deploy file.

The truncated table uses 4+4 character sha256 hashes (`a3f9…2c1b`) for readability; the full-64-char-hex block is what `apply-fix` byte-matches against. Producing the truncated table without the full block produces a malformed plan that `apply-fix` Step 4b.0.i will reject.
