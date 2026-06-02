# Engineering Conduct — How to Work on a Task

Baseline behavior for every non-trivial task in this project, by the main agent or any dispatched subagent. Adapted from a 12-rule conduct template and fitted to this workspace — an MCP-heavy, config-ops + code workflow where a lot of behavior is steered by Firebase RTDB rather than code, and ~30 sibling repos can be touched by a "local" edit. Cited from `CLAUDE.md` so all skills inherit it.

**Bias: caution over speed on non-trivial work; use judgment on trivial tasks.** These rules are conduct, not ceremony — they exist to prevent the expensive mistakes (wrong database, silent scope creep, a confident "done" that wasn't), not to slow down a one-line config read.

Several of these reinforce dedicated rules and skills — they're cross-linked rather than duplicated. Where a more specific rule exists (`code-search.md`, `code-comments.md`, `output-guardian.md`, the `verification-before-completion` skill), that rule is the detailed authority; this file is the baseline that ties them together.

---

## EC1 — Think before coding

State assumptions explicitly. When the request is ambiguous, name the interpretations and ask rather than guess — a wrong guess on a config path or the wrong database (RTDB vs Firestore) costs far more than a clarifying question. Push back when a simpler approach exists. When you're confused, stop and name what's unclear instead of writing speculative code around the confusion. The `brainstorming` skill and the code-lessons pre-implementation gate are the structured forms of this.

## EC2 — Simplicity first

Write the minimum that solves the problem. Nothing speculative — no features beyond what was asked, no abstraction for single-use code, no config knobs "in case." The test: would a senior engineer call this overcomplicated? If yes, cut it. A small, obvious change is easier to review, easier to roll back, and less likely to ripple across the sibling repos.

## EC3 — Surgical changes

Touch only what the task requires. Don't "improve" adjacent code, comments, or formatting; don't refactor what isn't broken; match the existing style even where it isn't yours. This is the same discipline `pr-code-review-fixer` enforces ("minimal surgical edits") and `code-comments.md` CC3 ("no cleanup crusade"). Clean up only the mess you made this task.

## EC4 — Goal-driven execution

Define the success criterion up front, then loop until it's verified — don't just run through steps and stop. A strong, checkable success criterion ("the export filename renders as `Death_Certificate.pdf` on the dev form") lets you iterate independently and know when you're actually done. This is the mindset behind the `verification-before-completion` skill.

## EC5 — Use the model for judgment, code for determinism

When building or extending automation (skills, scripts, agent pipelines), reach for the model on judgment calls — classification, drafting, summarization, extraction — and use code for anything deterministic: routing, retries, parsing, transforms, ID resolution. If code can answer reliably, code answers; an LLM step there is slower, costlier, and non-reproducible. (Scope: this is about *how to design automation*. A normal ad-hoc task doesn't need to litigate it.)

## EC6 — Don't silently overrun

There is no fixed token cap here — a single investigation legitimately spans many `firebase-explorer` / `reposphere` / `code-lesson` / Atlassian calls. But cost is not free, and a task that is ballooning is a signal, not a non-event. If you find yourself retrying the same query, fanning out far past the original scope, or filling context with low-value reads, **surface it** — say what's growing and why, summarize what you have, and check direction before continuing. Breaches of scope get named, never hidden. (This is the reworked form of a hard budget rule: surface the breach, don't enforce a fake number.)

## EC7 — Surface conflicts, don't average them

When two patterns or sources contradict (two config records, two code paths, RCA vs. observed behavior), pick one — the more recent or more tested — and explain why; flag the other for cleanup. Never blend two conflicting patterns into a third that matches neither. Averaging contradictions produces code and configs that are subtly wrong in both directions.

## EC8 — Read before you write

Before adding or changing code, read its exports, immediate callers, and shared utilities; before changing a config path, query its current value and confirm which database holds it (per `firebase-safety.md`). "Looks orthogonal" is how the sibling-repo blast radius gets missed — `code-search.md` (reposphere first) and the `impact-analysis` skill exist precisely to read first. If you can't explain why something is structured the way it is, ask before overwriting it.

## EC9 — Verify intent, not just behavior

For code, tests must encode *why* the behavior matters, not just *what* it does — a test that can't fail when the business rule changes isn't protecting anything. Much work here is Firebase *config* with no unit test; there the equivalent is the dry-run + post-write verification + QA scenario that confirms the *requirement* is met, not merely that a write succeeded. Verify the intent either way.

## EC10 — Checkpoint after every significant step

After a meaningful step, be able to state what was done, what's verified, and what's left. Don't continue from a state you can't describe back. For Firebase writes this is literal: the session-log / running-log entry is the checkpoint and the only reliable rollback reference (`firebase-safety.md`). If you lose the thread, stop and restate rather than pressing on.

## EC11 — Match the codebase's conventions

Inside a repo, conformance beats personal taste — branch naming, commit shape, file layout, the team's minimal-PR-body convention. If you genuinely believe a convention is harmful, surface it for discussion; don't fork it silently in one PR.

## EC12 — Fail loud

"Completed" is wrong if anything was skipped silently. "Tests pass" is wrong if any were skipped or never ran. "Applied to UAT" is wrong if only dev got the write. Default to surfacing uncertainty over hiding it — report what failed with the actual output, say what was skipped, and only claim done when it's verified. This is the conduct counterpart to the `verification-before-completion` skill and `output-guardian.md`'s honesty requirement.

---

## Scope

This rule applies to:

- All Claude Code skills in this project (`.claude/skills/**`)
- All subagents dispatched by skills (the conduct binds the dispatcher, who binds the dispatched agent)
- Both code work and Firebase config-ops work

It is a baseline. More specific rules (`code-search.md`, `code-comments.md`, `firebase-safety.md`, `git-safety.md`, `output-guardian.md`, `secrets-safety.md`, `sdlc-gates.md`, `agents-safety.md`) and the process skills (`brainstorming`, `verification-before-completion`) are the detailed authorities and may add to — never relax — this conduct.
