# Drive Upload of deploy-result.md (apply-fix Step 4h)

Mirror the just-written `deploy-result.md` to a shared Google Drive folder so the team lead can review it from their reader skill.

**Called by:** `apply-fix` SKILL.md, immediately after Step 4g (Output Guardian pass), and only when SKILL.md's Step 4h env + mode gate passed.

**Run-mode + env gating (enforced by SKILL.md Step 4h before this reference is consulted):**
- **DRY-RUN (any env):** SKILL.md skips this reference entirely. No prompt, no upload — dry-run plans are local-only and would pollute the lead's report queue.
- **REAL + env=`dev`:** SKILL.md skips this reference entirely. No prompt, no upload — dev applies are testbed runs and stay local. The local `deploy-result.md` is still written by SKILL.md Step 4f.
- **REAL + env=`uat` or `prod`:** SKILL.md invokes this reference. ASK the user per run. Never automatic.

If this reference is somehow invoked under one of the skipped conditions, refuse and surface the gate violation to the user — never assume the gate was lifted on purpose.

**Config file:** `.claude/skills/_shared/config/drive.json`. Schema:

```json
{
  "deploy_result_parent_folder_id": "<Google Drive folder ID — used by this step>",
  "template_assets_parent_folder_id": "<Google Drive folder ID — used by Step 4i; written by /prepare-uat Step 6.5>"
}
```

This step consumes the `deploy_result_parent_folder_id` key. Other keys (e.g. `template_assets_parent_folder_id`) are preserved on write — never blow away the file.

---

## Step 4h.0 — Ask the user and resolve the Drive folder (REAL only)

Read `.claude/skills/_shared/config/drive.json` to know the current cached folder.

**Cached path (file exists and id is populated)** — ONE combined prompt:

```
Upload {TICKET_KEY}-deploy-result.md to Google Drive?
Folder: https://drive.google.com/drive/folders/{cached_id}
  yes           — upload to this folder
  yes:<URL>     — upload to a different folder (updates cache)
  no            — skip upload
```

Parse the response:

- `no` → skip the rest of Step 4h. The local file remains the source of truth. In Step 7, report `Drive mirror: skipped — user declined`. Continue to Step 5 / Step 7.
- `yes` → use the cached id. Continue to Step 4h.ii.
- `yes:<URL or id>` → parse the new id (if a full URL, extract the segment after `/folders/`). Validate via `get_file_metadata(file_id: "<id>")` and confirm `mime_type` is `application/vnd.google-apps.folder`. On failure, surface the error and re-prompt. Once valid, overwrite `.claude/skills/_shared/config/drive.json` with the new id and tell the user `Saved — will use this folder for upload.`. Continue to Step 4h.ii.

**First-time-setup path (config file missing or id empty)** — TWO prompts, because we cannot show a folder we do not yet know:

1. Opt-in: `Upload {TICKET_KEY}-deploy-result.md to Google Drive? (yes / no)`
   - `no` → skip Step 4h. Step 7 reports `Drive mirror: skipped — user declined`.
   - `yes` → continue.
2. Folder setup: `Google Drive parent folder for deploy results is not configured. Paste the folder URL or ID (e.g. https://drive.google.com/drive/folders/1AbCdEf... or just 1AbCdEf...):`
   - Parse the id (extract the `/folders/<id>` segment if a URL is given).
   - Validate via `get_file_metadata(file_id: "<id>")` and confirm `mime_type` is `application/vnd.google-apps.folder`. Re-prompt on failure.
   - Write to `.claude/skills/_shared/config/drive.json` with the schema above. Tell the user `Saved. Future apply-fix runs will pre-fill this folder.`.
   - Continue to Step 4h.ii.

Either path resolves a `parent_folder_id` that Step 4h.ii reuses.

## Step 4h.ii — Detect existing file with the same name

The team has chosen a flat naming convention: every ticket's result lives at `{TICKET_KEY}-deploy-result.md` directly under the parent folder (no per-ticket subfolders).

Search for any existing file with that exact name in the parent folder:

```
search_files(query: "name = '{TICKET_KEY}-deploy-result.md' and '{parent_folder_id}' in parents and trashed = false")
```

Capture the result count:

| Existing files | Behaviour |
|---|---|
| 0 | Proceed to 4h.iii — fresh upload. |
| 1 | Surface to the user: `Drive already has a file named {TICKET_KEY}-deploy-result.md (id: <existing_id>, modified <date>). The available Drive MCP cannot replace or version-update this file — uploading will create a duplicate with the same name. Choose: (replace — I will rename the old file manually after / keep-both / abort).` Wait for the response. On `abort` stop here and report the file was saved locally only. On `replace` or `keep-both` continue. |
| 2+ | Surface the duplicates and ask: `Multiple files named {TICKET_KEY}-deploy-result.md already exist in the Drive folder. Manual cleanup is recommended before another upload. Continue anyway? (yes / no)`. On `no`, stop. |

## Step 4h.iii — Slice to latest run, then upload

Before uploading, slice out earlier runs so the Drive copy only carries the latest one — the local file stays the cumulative ledger. Do NOT re-read the full file and slice it by hand; run this deterministic one-liner (it emits the file's header block plus the last `^## Run ` block) to a scratchpad file, then upload that output:

```bash
awk 'BEGIN{header=1} /^## Run /{header=0; n++; block=""} header{printf "%s\n", $0; next} {block=block $0 "\n"} END{printf "%s", block; if(n>=2) printf "\n_Earlier runs are preserved in the deploy history._\n"}' tickets/{TICKET_KEY}/deploy-result.md > {SCRATCHPAD}/{TICKET_KEY}-deploy-result-upload.md
```

Behavior (matches the old model-driven algorithm exactly):

- **0 `## Run ` headings** → payload is the full file (single-run files upload as-is).
- **1 heading** → header block + that run, no trailer.
- **≥2 headings** → header block + LAST run block + the trailer line `_Earlier runs are preserved in the deploy history._` — intermediate runs (Run 1 … Run N-1) are excluded from the Drive copy.

Then upload the sliced payload:

```
create_file(
  name: "{TICKET_KEY}-deploy-result.md",
  parent_id: "{parent_folder_id}",
  mime_type: "text/markdown",
  content: "<sliced upload payload from the algorithm above>"
)
```

Capture the returned file id and `webViewLink` (or equivalent URL).

The local file at `tickets/{TICKET_KEY}/deploy-result.md` is NOT modified by the slicing step — devs continue to see the full multi-run ledger locally.

## Step 4h.iv — Report to user (do NOT modify the local file)

After upload, tell the user:

```
Uploaded to Google Drive:
  {DRIVE_WEB_URL}
```

Do not embed the Drive URL inside the local `deploy-result.md` — the local file is the source of truth and gets re-uploaded on every subsequent run; keeping the URL out of the body avoids self-referential drift. The local Notes section may mention "uploaded to Drive on YYYY-MM-DD HH:MM" for human traceability, but never paste the full URL there.

## Failure handling

If `create_file` returns an error, surface it verbatim. Do NOT retry silently — the local file is intact, and the user can re-run upload manually. Apply-fix's overall outcome is still successful (the Firebase writes already landed); the Drive mirror is supplementary.

If the MCP returns a secret or auth value in any field (per `.claude/rules/secrets-safety.md`), redact before continuing.
