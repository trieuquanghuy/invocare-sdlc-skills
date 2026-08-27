# Superpowers integration

This skill borrows discipline from several superpowers skills rather than reinventing it. Invoke them through the `Skill` tool when their trigger conditions fit. They are stricter than this skill's own prose — that is intentional.

The superpowers plugin is installed at `~/.claude/plugins/cache/claude-plugins-official/superpowers/`. Skills are referenced by their fully-qualified name `superpowers:<skill-name>`.

## Mapping

| This skill's step | Superpowers skill | How it applies |
|---|---|---|
| Step 7 — Verify | `superpowers:verification-before-completion` | Required reading before claiming any comment is "resolved." Its iron law — *no completion claims without fresh verification evidence* — applies per-comment, not just at the end of the run. |
| Step 6 — Apply (for `behavioral` bucket exception) | `superpowers:test-driven-development` | The `behavioral` exception requires writing a failing test first. TDD's "watch it fail" discipline is the safety mechanism that justifies the narrow exception. |
| Phase 1 Step 2 — Research (optional aid for `behavioral`) | `superpowers:systematic-debugging` | When the Firebase probe rules out config and the comment is a credible bug, use systematic-debugging's "root cause before fix" framing to validate the bug before committing to the four-criterion exception path. |
| Multi-comment processing | — | Process comments sequentially in the primary execution. Do not delegate edits or create worktrees; each fix must complete its own verification before the next begins. |
| End-of-run handoff | — | Return the read-only fix/escalation summary. Branch, push, merge, and pull-request actions require a separate explicit user request. |

`superpowers:requesting-code-review` and `superpowers:receiving-code-review` are not part of this skill's loop — they live on either side of it.

## Per-project verification commands

The `verification-before-completion` skill demands "the FULL command, fresh, complete." For this workspace, the right command depends on which project the edit landed in.

| Project | Verification command |
|---|---|
| `FCRM-Web` | `npm run lint && npm test` |
| `FCRM-Cloud-App` | `npm run lint && npm test` |
| `FCRM-Email-API`, `FCRM-Search-API`, `FCRM-Reports-API`, `FCRM-Exports-API`, `FCRM-Files-API`, `FCRM-Funeral-Services-API` | `npm run lint && npm test` (where configured) |
| `FCRM-Cloud-Functions` | `npm run lint && npm test` |
| `Barndoor-Batch-App`, `Barndoor-Tributes-App`, `Barndoor-Docs-App`, `Barndoor-Entities-App`, `Barndoor-SCIM-App` | `npm run lint && npm test` (NestJS — also check that the TS build succeeds: `npm run build`) |
| `FCRM-Document-Signer` | Node 14; `npm test` (Angular 8 legacy — lint may not be configured). |
| `pdf-mapper` | Node 14; `npm test` (Angular 10). |
| `vic-bdm-services`, `nsw-bdm-services` | Auto-escalate (hard rule #9). Verification commands deliberately not listed. |
| `FCRM-Barndoor-Infra` | Auto-escalate. |
| `FireHawk-Infra-Configs` | Auto-escalate. |

Always check `.nvmrc` / `engines` first. Run commands from the project's own directory — there is no root-level `npm test`.

If a project does not have lint or tests configured (some legacy projects don't), say so in the verification report rather than treating "no command available" as "verification passed." The `verification-before-completion` skill is explicit that absence of evidence is not evidence of absence.

## When NOT to delegate to a superpowers skill

These superpowers skills are powerful but wrong for the per-comment loop:

- **`superpowers:brainstorming`** — this skill is intentionally non-creative. Per-comment edits are not a place to brainstorm; the comment specifies the change. Brainstorming might be appropriate at a higher level (the user is deciding how to triage 50 comments across 4 PRs) but never inside the per-comment workflow.
- **`superpowers:writing-plans`** — comments are atomic edit units. A plan is overkill. The "Plan" step in this skill's workflow is one declarative sentence, not a multi-step plan doc.
- **`superpowers:executing-plans`** — same reason; the unit of work is too small.

If you find yourself wanting to invoke any of those mid-loop, that is a strong signal the comment is actually a refactor in disguise — escalate.
