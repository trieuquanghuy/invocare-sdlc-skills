# Template Artifact Resolution (apply-fix Step 4b.0)

Resolve `<ARTIFACT T_id ...>` placeholders before the per-write loop runs.

**Called by:** `apply-fix` SKILL.md, between Step 4a.5 (running-log append) and Step 4b.i (per-write read). Runs **once** per `/apply-fix` invocation, in **both REAL and DRY-RUN** modes.

**Skip when:** the deploy file has no `## Template Artifacts` section.

**Wire-format contract:** [`_shared/references/template-artifact-protocol.md`](../../_shared/references/template-artifact-protocol.md) — defines `T_id` naming, table format, full-sha256 block format, classification taxonomy, `<ARTIFACT T_id ...>` placeholder syntax, and Before/After integrity record format. This file is the **consumer** side; everything documented in the protocol is what this skill must parse and validate.

## Purpose

The deploy plan declares twig/css contents by reference (placeholders + a full-sha256 block per the protocol), not by inlining 12-45 KB of file content. This sub-step must:

1. Parse the protocol's Template Artifacts section.
2. Hash-verify local files against the plan's recorded full sha256.
3. Decide what to do when local has drifted.
4. Validate placeholder references against the artifact map.
5. Build an in-memory artifact map that Step 4b.iii consumes when substituting placeholders into the actual write payload.

## Session-cleanup invariant for STOPs in this sub-step

Step 4a created a session and Step 4a.5 appended a running-log line *before* this sub-step ran (REAL mode only). Every STOP path inside this sub-step (malformed full-sha256 block, missing local file, drift-prompt option `b` or `c`, undefined T_id, `(unchanged)` reference) MUST close the empty session before exit:

```
complete_session(session_id: "{SESSION_ID}")
```

Then append a `Run N — aborted at Step 4b.0` entry to `tickets/{TICKET_KEY}/session-log.md` (per Step 4d's template) recording: env, session_id, the specific 4b.0 STOP reason, and that NO writes occurred. The running-log line from 4a.5 stays as-is; the session-log run entry is what proves the abort was clean. On DRY-RUN, no session was created and no log mutation happens — the STOP just exits.

This invariant prevents an orphan session from sitting open after a malformed-plan abort. Without it, a later `rollback_session` call could not enumerate the writes to revert (there are none) but the session is also not formally closed, leaving the running-log line as the only artifact — which is acceptable but messy.

---

## Step 4b.0.i — Parse the Template Artifacts section

Extract two structures per the protocol's format:

1. The truncated table — for human-readable reporting in Step 4f / Step 7.
2. The **full-sha256 block** — the authoritative integrity record (full 64-char hex per file).

If the truncated table is present but the full-sha256 block is missing — **STOP**. The deploy plan is malformed. Surface: `Deploy plan has a Template Artifacts table but no full-sha256 block. Re-run /prepare-uat to regenerate the plan.` Do NOT create a session.

(Why the truncated table is not enough on its own: 4+4 char truncation has a 16⁸ collision space — reachable. The full block is mandatory per the protocol.)

Build an in-memory artifact map keyed by `T_id`:

```
T1 → { name: "Memorial Slideshow Cover", files: "twig+css", class: "new",
       twig_sha256_plan: "<full hex>", css_sha256_plan: "<full hex>",
       linked_write: "Step 2.1", twig_drive_url: "...", css_drive_url: "..." }
T2 → { name: "Cremation Booking Form", files: "twig", class: "update — twig only",
       twig_sha256_plan: "<full hex>", css_sha256_plan: "(unchanged)",
       linked_write: "Step 2.2", twig_drive_url: "...", css_drive_url: "(unchanged — not uploaded)" }
```

Files marked `(unchanged)` or `(none)` in the protocol carry no sha256 — those slots are flags, not hashes.

## Step 4b.0.ii — Verify local files exist and hash-match

For each artifact and each file the plan claims is in use (`twig` and/or `css` — skip files where the plan records `(unchanged)` or `(none)`):

1. Compute the local path: `document-templates/{name}/{name}.{twig|css}`.
2. **Local-file existence check.** If the file does NOT exist, STOP. Surface: `Template artifact {T_id} {twig|css} expected at document-templates/{name}/{name}.{twig|css} but the local file is missing. The deploy plan can't be applied without it. Sync the repo (git pull / branch switch) or correct the path on the source Confluence page, then re-run.` Do NOT create a session.
3. **Compute current sha256.** Use `shasum -a 256 "{path}"` and read the 64-char hex digest.
4. **Compare to the plan's full sha256.**

| Plan sha256 | Local sha256 | Outcome |
|---|---|---|
| Identical (full 64 chars match) | — | **OK.** Read the file bytes into the artifact map's `{twig\|css}_content` slot. Record `{twig\|css}_drifted: false`. |
| Differ | — | **Drift.** Surface the prompt below, wait for the user, do NOT silently substitute. |

**Drift prompt (one per drifted file):**

```
Template artifact {T_id} ({name}) — {twig|css} has drifted since the deploy plan was prepared.

  Plan sha256:  {first 16 chars}…{last 16 chars}
  Local sha256: {first 16 chars}…{last 16 chars}
  Local size:   {N KB}
  Plan size:    {N KB}

The local file is what apply-fix would inject into the Firebase write.

Options:
  (a) accept current local content and continue — drift recorded under deploy-result.md Notes; Step 4i will offer to re-upload to Drive
  (b) abort and re-run /prepare-uat to regenerate the plan against the current local file
  (c) abort — I want to check git for unintended changes first

Choose (a / b / c):
```

- `a` → store the local content in the artifact map; set `{twig|css}_drifted: true` and record `local_sha256: <full hex>` alongside `plan_sha256`. Continue.
- `b` → exit immediately. No session was created (4a is REAL-only and we're still pre-loop; on dry-run it was already skipped). Surface: `Aborted. Re-run /prepare-uat {TICKET_KEY} to regenerate the deploy plan.` Stop.
- `c` → same as `b` (graceful abort). Surface: `Aborted. Check git status / git log for unexpected changes to document-templates/{name}/, then re-run /prepare-uat or /apply-fix as appropriate.`

**Never** auto-pick `a`. **Never** continue silently. **Never** treat the plan's sha256 as authoritative over the local file — the local file is the source of truth for what gets written; the plan's hash is the integrity check, not the content.

## Step 4b.0.iii — Validate placeholder references in `data: {}` blocks

Scan every `data: {}` block in the Execution Steps. For each `<ARTIFACT T_id {twig|css}>` placeholder found (per the protocol's placeholder syntax):

- The `T_id` must appear in the artifact map built in 4b.0.i. If a placeholder references `T7` but the map only has `T1` and `T2` — STOP. Surface: `Step {N}.{i} references <ARTIFACT T7 ...> but T7 is not defined in the Template Artifacts section. Deploy plan is internally inconsistent — re-run /prepare-uat.` No session, no writes.
- The `{twig|css}` slot must have content in the artifact map (i.e. the plan recorded a real hash for that file, not `(unchanged)` or `(none)`). If a placeholder asks for `<ARTIFACT T2 css>` but the map records T2's css as `(unchanged)` — STOP, same surface.

## Step 4b.0.iv — Output and proceed

In-memory state ready for Step 4b.iii:

```
artifact_map = {
  T1: { ..., twig_content: <12288 bytes>, css_content: <3072 bytes>, twig_drifted: false, css_drifted: false },
  T2: { ..., twig_content: <46080 bytes>, css_content: null (unchanged), twig_drifted: true, css_drifted: false }
}
drift_summary = "1 file drifted: T2.twig (local 46080 B, plan 45056 B). See Step 4i."
```

Continue to Step 4b — the per-write loop now has everything it needs to substitute placeholders safely.
