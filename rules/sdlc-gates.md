# SDLC Gates — Mandatory MCP Calls Per Lifecycle Stage

Maps each SDLC stage to the MCP gate that must precede or accompany work at that stage. This is the **index**; it does not restate mechanics that live elsewhere. Two authorities own the detail:

- **Code-Lessons skim→fetch sequence, skip list, and self-audit** → `CLAUDE.md` "Code-Lessons MCP" section (canonical — do not duplicate here).
- **Code search before editing (reposphere first, grep fallback)** → `code-search.md`.

This file adds what those don't cover: the per-stage map, the PR-review `code-review` MCP flow (Stage S3), and the Layer-2 hook enforcement.

---

## Stage → gate map

| Stage | What's happening | Gate | Detailed authority |
|-------|------------------|------|--------------------|
| **S0** Planning / spec | RCA, spec, design — no code edited | none | — |
| **S1** Implementation (pre-edit) | about to `Edit`/`Write` code | `code-lesson` skim→fetch **before** the edit | `CLAUDE.md` Code-Lessons section + `code-search.md` |
| **S2** Self-review (pre-commit) | diff written, not yet done | re-skim the same lessons against the diff **AND** re-check it against CQ1–CQ12 | `CLAUDE.md` Code-Lessons section + `code-quality.md` |
| **S3** PR opened (org AI review) | reviewing an open PR | `code-review` 8-step flow (below) | this file |
| **S4** Addressing PR feedback | pushing fixes to a reviewed PR | `get_open_comments` **AND** the full S1 skim→fetch | `CLAUDE.md` Code-Lessons section |
| **S5** Merge / post-merge | merging | none (post-merge defect re-enters at S0) | — |

**S1 / S2 / S4 mechanics are NOT repeated here.** The skim is two severity calls (`high` AND `medium`, exclusive filter), then `get_lessons_by_ids`, applied as constraints — see `CLAUDE.md`. The per-task scope, the skip list, and the done-summary self-audit are all defined there too. Running only `high` on a logic change, or reusing a prior task's pull, are gate failures per that section.

S2 has a second, non-lesson companion: re-read the diff against the concrete code-quality standards in `code-quality.md` (CQ1–CQ12) and name the checks applied in the done-summary. The lesson re-skim reports what the org has learned; the CQ self-review reports whether this specific diff is correct, well-built, and in-scope. Both are part of S2.

S4 is the one stage with two distinct required calls: `get_open_comments(pullRequestId)` (manager-hub CUID, not the GitHub number — reports what the reviewer already raised) **plus** the S1 skim→fetch for the new diff scope (reports what the org has learned about this change shape). Neither substitutes for the other.

---

## Stage S3 — PR opened (org AI review): the `code-review` MCP 8-step flow

When reviewing someone else's open PR (or requesting a fresh AI review of your own):

1. `mcp__code-review__mh_list_open_prs` — pick a PR, capture its `prId` (manager-hub CUID, NOT the GitHub number)
2. `mcp__code-review__mh_start_review({ prId })` — get clone+checkout instructions
3. Bash: `git clone` + `git checkout` per the returned instructions
4. `mcp__code-review__mh_report_checkout({ executionId, localPath })` — server returns the review prompt + filenames
5. Bash: write the open-comments JSON (populated via `mcp__code-lesson__get_open_comments(prId)`), invoke the `claude` CLI with the returned prompt, read the result file
6. `mcp__code-review__mh_submit_result({ executionId, ... })`

Required permissions on the executing machine: `Bash(git:*)` and `Bash(claude:*)`. Always pass the `prId` CUID from `mh_list_open_prs` — never the GitHub PR number where the CUID is required.

---

## Layer-2 enforcement (hooks in `settings.local.json`)

The stage map above is prompt-level (Layer-1). A harness-level enforcement of the S1 gate is wired via three hooks in `.claude/settings.local.json`:

- **`UserPromptSubmit`** clears a per-session sentinel file, so each new task re-arms the gate
- **`PostToolUse`** writes the sentinel when any `mcp__code-lesson__*` or `mcp__code-lesson-kms__*` tool runs (skim, fetch, or `get_open_comments` all satisfy the gate)
- **`PreToolUse`** on `Edit|Write` BLOCKS the edit when the file is a code file AND the sentinel is missing — emits a deny decision pointing at this rule

The implementation lives in `.claude/scripts/sdlc-gate.sh`. The hook honors the `CLAUDE.md` skip list path-wise (`tickets/`, `.planning/`, `sessions/`, `.claude/`, `.git/`, `node_modules/`, `dist/`, `build/` excluded) and extension-wise (markdown / JSON / YAML / env files excluded).

To temporarily disable the Layer-2 gate, comment out the `PreToolUse` hook entry in `settings.local.json` or rename the gate script. The Layer-1 rule still applies — disabling the hook removes the hard stop, not the obligation.

---

## Scope

Applies to all skills (`.claude/skills/**`), all subagents they dispatch (per `agents-safety.md` A1, dispatch prompts cite this rule alongside `output-guardian.md` and `secrets-safety.md` when the task may edit code), and all editing tool calls (`Edit`, `Write`, `NotebookEdit`). Skills may add stricter conventions; they may not relax these gates.
