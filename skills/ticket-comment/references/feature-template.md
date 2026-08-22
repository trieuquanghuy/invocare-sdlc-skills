> **Brevity rule (author instruction — never include this block in the posted comment):** this comment is read by QA/BA skimming Jira. Include a table row, bullet, or sentence only when it tells the reader something actionable — omit filler rows, don't restate the same fact across sections, and keep prose to the template's stated length. A shorter comment that says everything real beats a complete-looking one padded to fill the template.

## 1. Requirement

{What BA specified — acceptance criteria, expected behavior, business rules}

## 2. What Was Implemented ({fix type: Config-only | Code-only | Code + config})

{Plain language summary of what was built — what the user/system can now do}

{Technical details — config paths, code changes, data flow, architecture decisions}

{code block or table: key changes where relevant — for config changes show before → after values, e.g. `filename: foo.pdf` → `bar.pdf`}

- {Bullet: what each change does — reference specific path/function/line}

{If implementation deviated from requirements, add:}
**Deviation:** {what BA specified vs what was actually built, and why}

## 3. Impact Area

> **QA** — areas to regression-test beyond this feature.
> **BA** — business workflows or pages affected by this change.

| Area | Impact | QA: What to Check | BA: What to Know |
|------|--------|-------------------|-----------------|
| {feature / page / module — e.g. "Funeral form — Page 3"} | Direct change | {specific thing to test} | {business workflow affected} |
| {adjacent feature that shares config or code} | Regression risk | {what to verify is unchanged} | {why BA should be aware} |

---

## UAT Deployment

> Fill in the block that matches your fix type. Delete the other two blocks.

---

### Config-only (no code deployment needed)

**Prerequisite:** Firebase write access to UAT environment

**ENV_SPECIFIC IDs — resolve before writing:**

| ID | How to find in UAT | Dev value |
|----|-------------------|-----------|
| `{RECORD_ID}` | In UAT: query `{parent_path}`, find the record where `{field}` = `"{value}"` | `{dev_id}` |

> Remove this table if all paths are STABLE (same across all environments).

**Steps:**
1. Resolve ENV_SPECIFIC IDs above (if any)
2. Dry-run — query each path to confirm current state matches expected
3. Apply config changes
4. Verify: {plain-language check in the app — e.g. "Open Funeral form, confirm field X shows Y"}

**Rollback:** Restore original values for each changed path (values listed in Implementation section above)

---

### Code-only (no Firebase config changes)

**PR:** [{PR title}]({PR_URL}) — merged to `main`

**Steps:**
1. Confirm PR is merged to `main`
2. Deploy to UAT: {pipeline name / branch / manual step}
3. Verify deployment: {what to check — navigate to feature, confirm behavior}

**Rollback:** Revert PR

---

### Mixed — ⚠️ deploy code FIRST, then config

> Applying config before the code is deployed will cause incorrect behaviour.

**PR:** [{PR title}]({PR_URL}) — merged to `main`

**ENV_SPECIFIC IDs — resolve before writing:**

| ID | How to find in UAT | Dev value |
|----|-------------------|-----------|
| `{RECORD_ID}` | In UAT: query `{parent_path}`, find the record where `{field}` = `"{value}"` | `{dev_id}` |

> Remove this table if all paths are STABLE.

**Steps:**
1. Confirm PR is merged to `main`
2. Deploy code to UAT: {pipeline name / manual step}
3. Verify code is live: {what to check — e.g. "navigate to feature, confirm page loads"}
4. Resolve ENV_SPECIFIC IDs above (if any)
5. Dry-run — query each path to confirm current state
6. Apply config changes
7. Verify: {full app check — e.g. "complete the flow end-to-end, confirm correct output"}

**Rollback:** Revert PR for code changes. For config: restore original values (listed in Implementation section above)

---

## 4. Session Deploy

**Session deploy**
- dev: 382 — 2026-05-26 14:50 — RTDB
- uat: 419 — 2026-05-28 09:10 — RTDB
- prod: 437 — 2026-05-29 11:20 — Firestore

> One row per `apply` session from `session-log.md` (action=apply only — never revert / re-apply rows), chronological. Use these IDs to revert if the change needs to be backed out.
>
> **Format rules:** the canonical row-format spec lives in [short-template.md](short-template.md) (`{SESSION_ROWS}` field rules). In brief: list bullets only (NEVER a table), row shape `- {env}: {session_id} — {YYYY-MM-DD HH:MM} — {DB}`, the trailing `— {DB}` target database required, no timezone label on the timestamp, backticks around `{session_id}` optional. Keep the `**Session deploy**` heading exactly as written — it's the marker that activates the Output Guardian carve-out at `.claude/rules/output-guardian.md`.

{Optional: ## 5. Screenshots
{images if available}}
