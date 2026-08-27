# Drive Upload for Template Assets (prepare-uat Step 6.5)

Mirror the twig/css files captured in Step 4.5 to a shared Google Drive folder so the BA / team lead can preview them while reviewing the deploy plan.

**Called by:** `prepare-uat` SKILL.md, after Step 6 (Output Guardian pass on the saved deploy file).

**Conditional gating:**
- Skip entirely when Step 4.5 was skipped (no template references on the Confluence page).
- Opt-in per run — never automatic.

**Why a separate flow from `apply-fix` Step 4h:** the pattern is similar (cached folder id, validate, slice, upload, capture URL) but writes to a separate config key (`template_assets_parent_folder_id`) so the two mirrors don't collide.

**Config file:** `.claude/skills/_shared/config/drive.json`. Schema this skill consumes:

```json
{
  "deploy_result_parent_folder_id": "<existing key — apply-fix Step 4h uses this>",
  "template_assets_parent_folder_id": "<NEW key — this skill uses this>"
}
```

Writes preserve both keys — never blow away `deploy_result_parent_folder_id`.

---

## Step 6.5.0 — Ask the user and resolve the Drive folder

Read `.claude/skills/_shared/config/drive.json`.

**Cached path** (file exists AND `template_assets_parent_folder_id` is populated) — ONE combined prompt:

```
Upload template artifacts ({N} files across {M} templates) to Google Drive for BA review?
Folder: https://drive.google.com/drive/folders/{cached_id}
  yes           — upload to this folder
  yes:<URL>     — upload to a different folder (updates cache)
  no            — skip upload
```

Parse the response per the apply-fix Step 4h conventions:

- `no` → skip the rest of Step 6.5. The deploy file's Template Artifacts table records `Drive mirror: skipped — user declined` under each template row's Drive URL slot. Continue to Step 7.
- `yes` → use the cached id. Continue to Step 6.5.ii.
- `yes:<URL or id>` → parse the new id (extract `/folders/<id>` from a full URL). Validate via `get_file_metadata(file_id: "<id>")` and confirm `mime_type` is `application/vnd.google-apps.folder`. Re-prompt on failure. Once valid, overwrite the `template_assets_parent_folder_id` key in `.claude/skills/_shared/config/drive.json` (preserve other keys — never blow away `deploy_result_parent_folder_id`) and tell the user `Saved — will use this folder for template uploads.`. Continue to Step 6.5.ii.

**First-time setup** (file missing OR `template_assets_parent_folder_id` empty) — TWO prompts:

1. Opt-in: `Upload template artifacts to Google Drive for BA review? (yes / no)`
   - `no` → skip Step 6.5. Template Artifacts rows record `Drive mirror: skipped — user declined`.
   - `yes` → continue.
2. Folder setup: `Google Drive parent folder for template assets is not configured. Paste the folder URL or ID:`
   - Parse the id (extract `/folders/<id>` from a URL).
   - Validate via `get_file_metadata` and confirm `mime_type` is `application/vnd.google-apps.folder`. Re-prompt on failure.
   - Write the `template_assets_parent_folder_id` key into `drive.json` (merge with existing keys; never overwrite the file blindly). Tell the user `Saved. Future prepare-uat runs will pre-fill this folder.`.
   - Continue to Step 6.5.ii.

## Step 6.5.ii — Detect existing files and handle collisions in one batch

For each template artifact (T1, T2, …) and each file (twig, css), the upload name is the source filename verbatim: `{Name}.twig` or `{Name}.css`. Issue ALL collision checks **in one parallel turn** — one `search_files` call per filename, sent together, never sequentially:

```
search_files(query: "name = '{Name}.{ext}' and '{parent_folder_id}' in parents and trashed = false")
```

Then present ONE consolidated collision prompt covering every file — never per-file prompts:

```
Drive collision check ({N} files):
  fresh (will upload):      {Name1}.twig, {Name1}.css
  1 existing duplicate:     {Name2}.twig (id: <existing_id>, modified <date>)
  2+ duplicates (cleanup):  {Name3}.css ({K} copies)

The Drive MCP cannot replace or version-update — uploading creates a duplicate with the same name.
For each colliding file, reply: replace (I will rename the old file manually after) / keep-both / skip — e.g. `{Name2}.twig: replace, {Name3}.css: skip`.
```

Per-file resolution: fresh files proceed to upload. On `skip` for a 1-duplicate file, record the existing file id + URL in the deploy file's Template Artifacts row and move on. On `replace` or `keep-both`, proceed to upload. On `skip` for a 2+-duplicates file, record `Drive mirror: ambiguous — {N} duplicates already in folder; cleanup needed` in the Template Artifacts row.

## Step 6.5.iii — Upload each file

For each file approved for upload, read the local bytes via the Read tool (or `cat`) and call:

```
create_file(
  name: "{Name}.{ext}",
  parent_id: "{template_assets_parent_folder_id}",
  mime_type: "{text/plain for .twig, text/css for .css}",
  content: "<full local file content, NOT escaped>"
)
```

Capture the returned `file_id` and `webViewLink` (or equivalent URL).

## Step 6.5.iv — Update the deploy file's Template Artifacts table

Re-open the saved `tickets/{TICKET_KEY}/{TICKET_KEY}-deploy-uat.md` and add two new columns to the Template Artifacts table (or update existing placeholder rows):

| ID | Name | … | twig Drive URL | css Drive URL |
|----|------|---|----------------|---------------|
| T1 | Memorial Slideshow Cover | … | https://drive.google.com/file/d/{id} | https://drive.google.com/file/d/{id} |
| T2 | Cremation Booking Form   | … | https://drive.google.com/file/d/{id} | (unchanged — not uploaded) |

For declined / failed / skipped uploads, the cell reads `skipped — user declined` / `failed: <reason>` / `skipped — duplicate ambiguity` respectively. The deploy file always carries a verdict in this column, never an empty cell — that's how the deployer knows whether to expect a Drive preview.

## Failure handling

If any `create_file` returns an error, surface it verbatim. Do NOT retry silently — the local deploy file is intact, and the user can re-run the upload manually. Step 6.5 failures do NOT block the deploy: the local twig/css are still the source of truth that apply-fix consumes; the Drive mirror is for human review only.

If the MCP returns a secret or auth value in any field (per `.claude/rules/secrets-safety.md`), redact before continuing.
