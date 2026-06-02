# Shared Checker Contract

This file defines the unified output contract for all checker subagents in the InvoCare skill set. Every checker (`apply-fix`, `create-rca`, `create-spec`, `create-pr`, `ticket-comment`, `publish-rca`) returns the same base shape so the calling skills can parse and act on results uniformly.

> **Source:** referenced by every `.claude/skills/*/checker-prompt.md`. Keep in sync.
> **Companion:** `.claude/skills/_shared/contracts/iteration-loop.md` for the standard 3-iteration verification loop used by artifact-generating skills.

---

## Verdict semantics

Three values, same meaning everywhere:

| Verdict | Meaning | Caller behavior |
|---------|---------|-----------------|
| `PASS` | No blockers, no warnings | Proceed silently |
| `WARN` | No blockers, ≥1 warning | Print warnings, ask user `Proceed anyway? (yes/no)` |
| `FAIL` | ≥1 blocker | Print blockers, exit. Do NOT proceed. |

`create-rca` adds an orthogonal `readiness` axis (`CLEAR` / `UNRESOLVED`) because the RCA's investigation can be technically complete (`verdict=PASS`) but still have open questions that block downstream `create-spec`. Other checkers MUST omit this field.

---

## Verdict logic

For checkers that classify gaps by severity:

- ≥1 gap with `severity: blocker` → `verdict: FAIL`
- 0 blockers AND ≥1 gap with `severity: warning` → `verdict: WARN`
- 0 blockers AND 0 warnings → `verdict: PASS`

`info`-level entries are advisory only and never affect the verdict.

---

## Canonical output schema

Every checker returns ONE fenced JSON block as the LAST block of its reply. No prose after.

```json
{
  "verdict": "PASS" | "WARN" | "FAIL",
  "ticket_key": "<from inputs, or null if not applicable>",
  "summary": "N blockers, M warnings",
  "iteration_hint": "short string for progress display",
  "gaps": [
    {
      "rule": "<rule id and short name, e.g. 'R7 — QUALITY-REPORT.md exists'>",
      "severity": "blocker" | "warning" | "info",
      "fixable": true | false,
      "issue": "<specific description, plain technical English>",
      "suggested_fix": "<what main agent should do, or null>",
      "evidence": "<file:line, optional>"
    }
  ]
}
```

### Field rules

- `verdict` MUST be one of `PASS`, `WARN`, `FAIL` — uppercase, no aliases
- `gaps[]` is REQUIRED — empty array `[]` if `verdict=PASS` with no findings
- `severity` MUST be one of `blocker`, `warning`, `info`
- `fixable` MUST be present on every gap. `true` means the calling skill can apply `suggested_fix` mechanically without re-investigating; `false` means human or fresh data is needed
- `suggested_fix` MUST be `null` when `fixable: false`
- `evidence` is optional but strongly recommended on blockers
- `iteration_hint` is the line printed between checker iterations (e.g. `"3 fixable, 1 unresolved"`)

---

## Per-checker extensions

Checkers MAY add fields beyond the base shape. Currently:

### Pre-flight checkers (apply-fix, create-pr)

May add:
- `target_env`: `"dev"` | `"uat"` | `"prod"` (apply-fix)
- `repo`: repo name (create-pr)
- `branch`: current branch name (create-pr)

### create-rca (artifact checker, runs in iteration loop)

Adds:
- `readiness`: `"CLEAR"` | `"UNRESOLVED"` — orthogonal axis. RCA can be complete (`verdict=PASS`) but still have open questions blocking downstream skills.

### create-spec (artifact checker, runs in iteration loop)

No extensions. `readiness` is intentionally NOT emitted — the spec checker is never dispatched when the RCA has open questions (precondition gate in `create-spec/SKILL.md` Step 1).

### Output Guardian linters (ticket-comment, publish-rca)

May add:
- `body_excerpt`: 80-char excerpt of the offending line, with secrets redacted to `<redacted>` per `secrets-safety.md`. Used in evidence only — not in `issue` or `suggested_fix`.

---

## Subagent dispatch

All checker dispatches MUST use the `pipeline-checker` subagent type (`.claude/agents/pipeline-checker.md`), not `general-purpose`. The pipeline-checker has a tool whitelist that excludes every write-side capability (Write, Edit, Firebase writes, Atlassian writes, gh/git writes, Task fanout). This converts the read-only-by-default rule from `agents-safety.md` A2 from a prompt-level guideline into a tool-level boundary.

The dispatch invocation in skill prose looks like:

```
Dispatch a pipeline-checker subagent with:
  - The full prompt from `./checker-prompt.md`
  - <skill-specific inputs>
```

Skills MUST NOT fall back to `general-purpose` unless `pipeline-checker` is genuinely unavailable (e.g. on a platform that doesn't support custom subagents). If falling back, surface the substitution to the user.

---

## Output Guardian

Every checker MUST apply `.claude/rules/output-guardian.md` to all `issue`, `suggested_fix`, `summary`, and `iteration_hint` text. NO tool names (`firebase-explorer`, MCP names), NO session IDs in user-facing strings, NO AI/Claude references. Session IDs MAY appear in `evidence` fields (internal audit trail) but never in `issue` or `suggested_fix`.

---

## Migration note (deprecated shapes)

Before the unification, three distinct schemas existed:

- `apply-fix`'s checker used `verdict + blockers[] + warnings[] + info[]` with `BLOCK` as a `FAIL` alias
- `create-rca`'s checker used `quality + readiness + gaps[]` (no `verdict`)
- `create-spec`'s checker used `quality + gaps[]` (no `verdict`)

These have all been migrated to the canonical `verdict + gaps[]` shape. The `BLOCK` alias, the `quality` field, and the split `blockers[]/warnings[]/info[]` arrays are NO LONGER VALID — calling skills should not parse them. If a checker emits any of those fields, treat it as a contract violation.

`readiness` is the only valid extension to the base shape and applies to `create-rca` only.
