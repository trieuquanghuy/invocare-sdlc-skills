# Re-upload Drifted Template Artifacts to Drive (apply-fix Step 4i)

When the BA edits a local twig/css after `/prepare-uat` uploaded a snapshot to Drive, the Drive mirror disagrees with what `apply-fix` actually wrote to Firebase. This step offers to re-mirror the local file so Drive matches Firebase.

**Called by:** `apply-fix` SKILL.md, after Step 4h (deploy-result Drive upload).

**Run-mode and conditional gating:** run only when ALL of the following hold —
- Step 4b.0 detected at least one drifted artifact (`drift_summary` is non-empty), AND
- The user chose option `(a) accept current local content` for that file, AND
- Mode is REAL.

Skip entirely otherwise:
- No Template Artifacts section in the deploy file → skip Step 4i.
- Template Artifacts section present but no drift → skip; the Drive copy already matches the local file and the Firebase write.
- DRY-RUN → skip; no real writes happened and re-uploading a mirror of a fictional deploy pollutes the lead's review queue.

**Config file:** `.claude/skills/_shared/config/drive.json`. This step consumes the `template_assets_parent_folder_id` key (NOT `deploy_result_parent_folder_id` used by Step 4h). Writes preserve both keys.

---

## Step 4i.0 — Confirm Drive folder is configured

Read `.claude/skills/_shared/config/drive.json`. If `template_assets_parent_folder_id` is missing OR empty:

```
Local template artifacts drifted but the Drive folder for template assets is not configured locally.
Drive re-upload skipped — the local file is the source of truth for the write that just landed.

To enable re-upload in future runs: paste the folder URL or ID now to save it for next time, or `skip` to continue without saving.
```

On `skip` → record `Drive mirror (templates): not configured` under Step 4f Notes; continue to Step 5. On URL/id → validate via `get_file_metadata` (must be a Drive folder); on success, write the new id under `template_assets_parent_folder_id` (merge — preserve `deploy_result_parent_folder_id`); on failure, surface verbatim and re-prompt.

## Step 4i.i — Per-drifted-file prompt

For each drifted file (e.g. `T2.twig` from Step 4b.0.ii):

```
Template artifact T2 ({name}) — twig drifted from the deploy plan.
The write that just landed on {ENV} used the LOCAL content (sha256 {first 8}…{last 8}, {N} KB).
The Drive mirror at {twig_drive_url} still holds the PRE-DRIFT version (sha256 {first 8}…{last 8}).

Re-upload the current local file to Drive so the mirror matches what landed on Firebase?
  (yes / no / abort)
```

- `yes` → continue to 4i.ii.
- `no` → record `Drive mirror (T2.twig): stale — user declined re-upload (plan sha256 = …, local sha256 = …)` under Step 4f Notes. Move to the next drifted file.
- `abort` → stop Step 4i. The Firebase writes have already landed (Step 4c completed the session). Record `Drive mirror (templates): re-upload aborted by user` under Step 4f Notes. Continue to Step 5.

## Step 4i.ii — Detect existing file with the same name and upload

For each file approved for re-upload, run the same collision-handling flow as Step 4h.ii (replace / keep-both / skip) but against the `template_assets_parent_folder_id` folder and the source filename verbatim (`{name}.{twig|css}`).

Upload via:

```
create_file(
  name: "{name}.{twig|css}",
  parent_id: "{template_assets_parent_folder_id}",
  mime_type: "{text/plain for .twig, text/css for .css}",
  content: "<full local file content>"
)
```

Capture the returned `webViewLink`. Record it in Step 4f under a `Template artifact mirror updates` section:

```
T2.twig:
  pre-drift Drive URL:  {old url}     (no longer matches Firebase)
  new Drive URL:        {new url}     (matches Firebase — sha256 {first 8}…{last 8})
  pre-drift plan hash:  {first 8}…{last 8}
  new local hash:       {first 8}…{last 8}
```

## Failure handling

If `create_file` returns an error, surface verbatim. Do NOT retry silently. The Firebase write already succeeded — the Drive mirror is supplementary. Record the failure under Step 4f Notes (`Drive re-upload (T2.twig): failed: <reason>`) and continue to the next file.

If the MCP returns a secret value in any field, redact before continuing (per `.claude/rules/secrets-safety.md`).
