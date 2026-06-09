# Output Guardian

Applies to every document, comment, or artifact written to Jira, Confluence, or any file shared with stakeholders. No exceptions.

## Never Expose Internal Tooling

Any output must read as if written by a developer — not an AI agent.

**Never include:**
- Tool names: `firebase-explorer`, MCP tools, or any Claude/AI tool reference
- Pipeline / agent / skill names: never name the internal automation that produced the work — no `pipeline`, `pipeline-checker`, `subagent`, `agent`, skill names (`/create-rca`, `/apply-fix`, `/create-pr`, `/ticket-comment`, etc.), or any reference to the workflow that generated the artifact. The reader sees a developer's output, not a description of how it was produced.
- Session identifiers: Firebase session IDs, run IDs, session numbers (e.g. "Session 124", "Session 127") — see the two Carve-outs below for the approved exceptions (`/ticket-comment` Session deploy section; `/create-release-report` Deploy history rows)
- Session-applied entries: lines like "Session 124 applied (AU/NZ At Need templates) — partial, wrong label/format/logic" must never appear in RCA documents, Jira comments, Confluence pages, or any stakeholder-facing file. That detail belongs in `session-log.md` only.
- Internal workflow language: "queried via", "using tool", "MCP call", "AI investigated", "Claude confirmed"
- Harness / chat artifacts: literal placeholders the harness injects into a conversation, e.g. `[Image #1]`, `[Image #2]`, `[Image: ...]`, "as shown in the screenshot above", or any token that only makes sense inside a Claude session. These leak the fact that an AI assembled the artifact and mean nothing to the reader. This applies to code comments and commit messages as well as prose (see `.claude/rules/code-comments.md`).
- Local artifact paths or filenames: NO references to `tickets/{KEY}/...`, `.claude/...`, `docs/...`, plain filenames like `spec.md` / `rca.md` / `deploy.md` / `validation.md` / `session-log.md` / `rollback.md`, relative paths like `./references/...`, or absolute paths like `/Users/.../...`. The reader doesn't have your workspace. Write everything inline. (Code repo paths like `FCRM-Web/src/forms/FormController.ts:42` are fine — the reader can find them via GitHub.)
- Any indication the author is an AI or that automation was involved

**Right:** "Config at `/core/funerals/forms/ABC` was updated — `filename` set to `foo.pdf`"
**Wrong:** "firebase-explorer confirmed `/core/funerals/forms/ABC` was updated in session `abc123`"
**Wrong:** "Session 124 applied (AU/NZ At Need templates) — partial, wrong label/format/logic"
**Wrong:** "See `tickets/GEN-2759/spec.md` Section 4 for the deployment steps."
**Right:** Paste the deployment steps inline; do not link to local files.

## Carve-out: `Session deploy` section in `/ticket-comment` comments (short AND full)

Session identifiers (the `session_id` returned by `create_session`) MAY appear in Jira comments produced by the `/ticket-comment` skill, but ONLY inside a `**Session deploy**` (or `### Session deploy`) section. The team lead authorized this exception so the dev / UAT / prod progress comments carry the rollback reference inline. The carve-out covers **both** comment flavors: the SHORT progress checkpoint and the FULL QA-handoff comment (bug-template / feature-template Section 7). The only purpose of the section is tracing and rollback — nothing else about the carve-out changes between flavors.

**The carve-out applies ONLY to:**
- `host: "jira-comment"` (the Output Guardian linter dispatched by `/ticket-comment`) — for BOTH the short and full templates
- Lines that sit between a `**Session deploy**` / `### Session deploy` heading and the next heading or end of body (in the full templates this is Section 7, which still carries the `**Session deploy**` marker line that activates the carve-out)
- Session IDs formatted as a compact list: `- {env}: {session_id} — {YYYY-MM-DD HH:MM} — {DB}` (one row per applied session; action=apply only — never include revert / re-apply rows). Each row carries three fields: the `session_id`, the apply timestamp, and the **target database** written in that session — `{DB}` is one of `RTDB`, `Firestore`, or `RTDB+Firestore` (use the combined form when the session wrote to both), derived from the write tool recorded in `session-log.md` (`write_rtdb` → RTDB, `write_firestore` → Firestore). Backticks around `{session_id}` are optional — short numeric IDs read cleaner without them; wrap longer alphanumeric or dash-containing IDs in backticks to avoid markdown ambiguity. Example rows:
  - `- dev: 382 — 2026-05-26 14:50 — RTDB`
  - `- uat: \`abc-456-xyz\` — 2026-05-29 09:10 — Firestore`

**The carve-out does NOT apply to:**
- Confluence pages (RCA pages, design docs, anything posted via `createConfluencePage` / `updateConfluencePage`) — session IDs stay forbidden
- Prose narration anywhere in any comment — session IDs may only appear inside the structured list under the `**Session deploy**` heading, never inline ("we ran session abc-123 then…" stays forbidden). This holds in both the short and full templates.
- Any other host (deploy-result.md prose, RCA documents, status reports, GitHub PR titles / bodies / commit messages, etc.)

A Jira comment that exposes any other piece of internal tooling (tool names, MCP calls, AI attribution, local artifact paths) still fails the linter — the carve-out is for the session-ID line items only.

## Carve-out: `Deploy history` rows in `/create-release-report` pages

Session identifiers (the `session_id` returned by `create_session`) MAY appear in release reports produced by the `/create-release-report` skill — in the LOCAL draft AND on the published Confluence page — but ONLY embedded in a `Deploy history:` block row. The team lead authorized this exception so each release line carries its per-session rollback reference inline. This is the one place session IDs are permitted on a Confluence page.

**The carve-out applies ONLY to:**
- `host: "confluence-page"` when the page is a release report produced by `/create-release-report` (title `Release Report: {DD MMM YYYY}`), AND the local draft of the same skill
- Lines that are `Deploy history:` block rows in the exact format `- {env} | {session_id}-{action} | {status} | {date}` (optionally followed by a trailing `(scope note)`). One row per session.
  - `{env}` is one of `dev` / `uat` / `prod` (lowercase)
  - `{session_id}` is alphanumeric, hyphens, dots, or underscores — no spaces — prefixed onto the action as `{session_id}-{action}`
  - `{action}` is one of `apply` / `re-apply` / `revert`
  - Example row: `- uat | 511-apply | Success | 2026-06-09 (supplier un-archive + 3 SKU tags)`

**The carve-out does NOT apply to:**
- Prose narration anywhere in the report — session IDs may only appear in the `Deploy history:` block rows, never inline in the executive summary, notes, or appendix.
- Any other Confluence page (RCA pages, design docs, anything not a `/create-release-report` release report) — session IDs stay forbidden.
- Any other host (RCA documents, status reports, GitHub PR titles / bodies / commit messages, etc.).

A release report that exposes any other piece of internal tooling (tool names, MCP calls, AI attribution, local artifact paths) still fails the linter — this carve-out is for the `Deploy history` session-ID rows only.

## Author Identity

All output reads as written by the developer who did the work (the ticket's assignee) — not by an AI. Never hardcode a specific person's name as the author, and never state or imply an AI wrote, investigated, or applied anything.

## Scope

Jira comments, Confluence pages, RCA documents, spec/deploy files, any file in `tickets/` shared externally, **and everything pushed to GitHub** — PR titles, PR bodies, and commit messages. A commit message or PR body that names a pipeline, agent, skill, or AI tool fails this rule the same way a Jira comment would; `/create-pr` enforces the subset that applies at PR-creation time (Rule 9 / P14), and this rule is the baseline behind it.
