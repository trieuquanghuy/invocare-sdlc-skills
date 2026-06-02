# Code Comments — Short, Optional, and Free of Harness Artifacts

Applies to every code edit made by the main agent or any dispatched subagent — feature work, bug fixes, refactors, review-feedback fixes, anything that adds or changes a comment in a source file. Cited from `CLAUDE.md` so all skills and agents inherit it.

The goal is code that reads as if a developer who knows the codebase wrote it: comments that earn their place, and never any token that only makes sense inside a Claude session.

---

## CC1 — Comments are optional; add one only when the code can't say it itself

Most lines don't need a comment. Well-named variables, small functions, and clear control flow explain themselves. Reach for a comment only when the *why* is genuinely non-obvious — a workaround, a subtle invariant, an ordering constraint, a reason the obvious approach was avoided.

Do NOT narrate *what* the next line does when the code already says it. `// increment the counter` above `count++` is noise.

**Prefer:** explaining a non-obvious reason.
```ts
// work on a copy so we never mutate the cached/shared field config
field = { ...field };
```

**Avoid:** restating the mechanics.
```ts
// spread field into a new object
field = { ...field };
```

---

## CC2 — Keep comments short

One line where one line will do. A comment that runs longer than the code it describes is usually a sign the code needs a better name or a small extract, not a paragraph. If a block genuinely needs extended explanation (a tricky algorithm, a regulatory rule), keep the inline comment to a single line and put the detail where the *team* will find it — the PR description, the ticket, or a design doc — not buried in the source.

---

## CC3 — No ticket keys in inline comments

Do not prefix or tag inline code comments with the Jira key (`// GEN-2920: ...`). The ticket linkage already lives where it belongs: the commit message, the branch name, and the PR. Repeating `GEN-2920:` on every changed line is visual noise that rots — six months later the key points at a closed ticket and tells the next reader nothing about the code in front of them.

**Prefer:**
```ts
field = { ...field };           // work on a copy so we never mutate the shared config
field.required = false;         // non-holders save cleanly
field.nullable = true;          // else the `required || !nullable` validator re-attaches
```

**Avoid:**
```ts
field = { ...field };           // GEN-2920: work on a copy so we never mutate the shared config
field.required = false;         // GEN-2920: strip required for non-holders
field.nullable = true;          // GEN-2920: also clear nullable:false
```

The lessons corpus and the wider repo may already carry historical comments with ticket keys — don't go on a cleanup crusade. This rule binds *new and modified* comments; leave untouched lines untouched.

---

## CC4 — Never write harness or chat artifacts into code

A comment (or any code) must never contain a token that only exists inside a Claude session. The most common offender: when a user pastes a screenshot, the harness renders it as `[Image #1]`, `[Image #2]`, `[Image: ...]`. That string must NEVER end up in a source file, comment, commit message, or PR.

Forbidden in any code artifact:
- `[Image #1]`, `[Image #2]`, `[Image: ...]`, or any image placeholder
- "as shown in the screenshot / image above", "per the attached image"
- Any reference to the conversation, the prompt, the user's message, or the fact that an assistant produced the change

This is the code-side counterpart to `.claude/rules/output-guardian.md`'s "Harness / chat artifacts" entry. If the *content* of a pasted image matters to a comment, describe the actual fact in plain language — never point at the image.

**Wrong:**
```ts
// fix the validator bug from [Image #1]
```
**Right:**
```ts
// clear nullable:false so the required-vs-nullable validator doesn't re-attach
```

---

## Scope

This rule applies to:

- All Claude Code skills in this project (`.claude/skills/**`) that edit source files
- All subagents dispatched by skills that may write code (per `agents-safety.md` A1, dispatch prompts that involve code edits should cite this rule alongside `output-guardian.md` and `secrets-safety.md`)
- Every source-file edit: `Edit`, `Write`, `NotebookEdit`

It does NOT govern prose docs (`tickets/`, `.planning/`, RCAs) — those are covered by `output-guardian.md`. It governs comments *inside code*.

Individual skills may add stricter conventions (e.g. a house style that bans inline comments entirely in a given file type). They MAY NOT relax this baseline.
