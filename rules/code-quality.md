# Code Quality — Concrete, Checkable Standards for Code Claude Writes

Applies to every source-file edit by the main agent or any dispatched subagent — features, bug fixes, refactors, review-fix edits. Cited from `CLAUDE.md` so all skills and agents inherit it.

This rule is the concrete, **checkable code-level layer**: the specifics a reviewer flags in a diff. It is the counterpart to `engineering-conduct.md` (which sets *conduct*) — that rule says "be surgical / simple / read first"; this one says exactly what "correct, well-built, in-scope code" looks like in this workspace's stack (TypeScript, React, Firebase, Node).

**It cross-links, never restates.** Where another rule owns a topic, CQ points at it:

| Topic | Owning authority |
|-------|------------------|
| Scope / surgical / YAGNI / matching conventions | `engineering-conduct.md` (EC2, EC3, EC8, EC11) |
| RTDB-vs-Firestore + write safety | `firebase-safety.md` |
| Comment style | `code-comments.md` |
| Blast-radius investigation (find callers first) | `impact-analysis` skill + `code-search.md` |

**Bias: caution over speed on non-trivial code; use judgment on trivial edits.** These are standards to prevent the expensive review issues, not ceremony for a one-line change — see the Skip list.

---

## Correctness / logic bugs

### CQ1 — Handle the empty, null, and error path before the happy path

Most logic bugs here are an unconsidered branch: a value that can be `undefined`, an array that can be empty, a request that can reject. Write the guard first.

- Prefer optional chaining / explicit guards over the non-null `!` assertion used only to silence the compiler — `!` hides exactly the case that breaks in production.
- `switch` over a union should be exhaustive with a `default` that throws (or an `assertNever`), so a new variant fails loudly instead of falling through.
- Never swallow a caught error silently. Handle it, rethrow it, or log it with context — an empty `catch {}` turns a failure into wrong data.

```ts
// Wrong — ! silences the compiler on the exact case that fails
const name = user!.profile!.displayName;
// Right — guard the path that can be missing
const name = user?.profile?.displayName ?? 'Unknown';
```

### CQ2 — Async correctness

- `await` every promise. A floating promise (called without `await`/`.catch`) loses errors and reorders effects.
- Independent awaits run with `Promise.all`; sequential `await` only when a later call depends on an earlier result.
- No `async` callback inside `Array.prototype.forEach` — it does not await, so errors escape and ordering is lost. Use a `for...of` loop or `Promise.all(map(...))`.
- Wrap awaits that can reject in `try/catch` at the boundary that can actually recover, not three frames too deep.

```ts
// Wrong — forEach does not await; rejections are unhandled, writes race
items.forEach(async (i) => { await save(i); });
// Right
await Promise.all(items.map((i) => save(i)));
```

### CQ3 — Validate data at boundaries

Treat API request payloads and Firebase reads as untrusted and possibly-missing — an RTDB path or Firestore doc may not exist, or may not have the shape you expect.

- Narrow types at the edge (a parse/guard), don't `as`-cast an `any`/`unknown` through the boundary and hope.
- A read that returns `null`/`undefined`/missing fields is a normal case, not an exception — handle it.

---

## Design principles

### CQ4 — KISS / YAGNI at the code level

Write the obvious implementation that solves the task. No abstraction, indirection layer, or config knob for a single current use. (Conduct authority: `engineering-conduct.md` EC2.) The test: would a senior reviewer call this overcomplicated for what it does? If yes, cut it.

### CQ5 — DRY by the rule of three

Extract a shared helper when the *same* logic genuinely repeats — the rule of three is a guideline, not a hard gate: pull it out at two sites if the logic is substantial or correctness-critical (a tax calc, a date parse), and tolerate a little duplication when the blocks are short and likely to diverge. The one thing to avoid is merging two *incidentally*-similar blocks into one flag-driven helper — that couples unrelated callers, and the next change to one of them re-forks it. When two blocks look similar but mean different things, keep them separate (ties to `engineering-conduct.md` EC7 — don't average two patterns into a third). Good abstraction that removes real, repeated complexity is the goal; only *premature* abstraction is the smell.

### CQ6 — Single responsibility; SOLID only where it removes real coupling

Each function/module should have one reason to change — single responsibility is the SOLID principle that pays off almost everywhere, so apply it freely. Reach for the rest of SOLID when there's a *named* reason: a real seam you need (a dependency you want to swap or mock in tests), a second implementation that genuinely exists or is clearly coming, or coupling you can point to and want to cut. That's good design, and it's worth doing proactively when the reason is real. What to avoid is the reflexive version — an interface, factory, or DI wrapper added for a single concrete implementation with no seam in sight is usually YAGNI (CQ4), not design. Introduce the abstraction when the second case or the test seam arrives, not before.

### CQ7 — Size is a signal

A function long enough to need scrolling, or a file doing several unrelated jobs, is doing too much — extract a well-named unit with a clear input/output. Smaller, well-bounded units are easier to review, test, and roll back.

---

## Style / consistency

### CQ8 — Match the surrounding code

Naming, import ordering, error-handling idiom, and file layout follow the file and repo you are editing — not personal taste (conduct authority: `engineering-conduct.md` EC11). Conformance beats preference inside a repo; if a convention is genuinely harmful, surface it, don't fork it silently in one PR.

### CQ9 — No leftover cruft in the diff

No commented-out code, dead branches, unused variables/imports, or leftover debug logging in the change. The diff should contain only lines that earn their place. "Debug logging" means a `console.log` (or equivalent) added to trace a value during development — not the repo's actual logging mechanism; where a service uses `console.*` or a logger as its real telemetry, intentional log lines stay. The test is intent: would this line still belong if someone else read the merged code?

### CQ10 — Names state intent

A boolean reads as a predicate (`isHolder`, `hasConsent`); a function name is a verb phrase (`buildExportFilename`). Avoid `data2`, `tmp`, `flag`, or abbreviations that need a comment to decode — a good name removes the need for the comment (see `code-comments.md` CC1).

---

## Scope / blast radius

### CQ11 — Surgical diff

Touch only what the task requires. No reformatting untouched lines, no "while I'm here" cleanups, no editing adjacent code that isn't broken (conduct authority: `engineering-conduct.md` EC3). Unrelated churn bloats review and hides the real change.

### CQ12 — Check the blast radius before editing shared code or config

A "local" edit is not local in this workspace — ~30 sibling repos and Firebase-config-driven behavior mean a shared change ripples. Before changing a shared util, an exported type/interface, or an RTDB/Firestore config path:

1. Find the callers/consumers first — reposphere first per `code-search.md` (`search_with_context`, `cross_repo_search`, `explore_neighborhood`).
2. Confirm which database holds a config value before editing it (`firebase-safety.md`).
3. State the impact in your summary. For a risky change, the `impact-analysis` skill is the structured form of this.

---

## Self-review before declaring done

Before claiming a code change is complete, re-read the diff against CQ1–CQ12 (this is the SDLC **S2** pre-commit gate companion to the code-lessons re-skim — see `sdlc-gates.md`). In the done-summary, **name which CQ checks you applied** to the diff (e.g. *"checked CQ1–CQ3 correctness and CQ11–CQ12 scope; CQ5 DRY n/a — no repetition introduced"*). Naming coverage lets a reviewer see what was checked, not just that you intended to. "Done" is wrong if a check was skipped silently (`engineering-conduct.md` EC12).

---

## Scope

This rule applies to:

- All Claude Code skills in this project (`.claude/skills/**`) that edit source files
- All subagents dispatched by skills that may write code (per `agents-safety.md` A1, code-writing dispatch prompts cite this rule alongside `output-guardian.md` and `secrets-safety.md`)
- Every source-file edit: `Edit`, `Write`, `NotebookEdit`

It is a baseline that **adds to, never relaxes**, the rules it cross-links. More specific rules (`firebase-safety.md`, `code-comments.md`, `engineering-conduct.md`) and the process skills remain the detailed authorities on their topics.

## Skip list (where the code-quality self-review may be omitted)

- Pure typo fixes in prose or identifiers (no logic touched)
- Comment-only edits (governed by `code-comments.md`)
- Pure whitespace / formatting changes
- Markdown / plain-text / config / env-file edits that contain no executable code

If the change touches any executable code path beyond this list — including a "one-line" fix — the CQ self-review is required. When in doubt: apply it.
