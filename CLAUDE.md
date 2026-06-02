@.claude/rules/output-guardian.md
@.claude/rules/firebase-safety.md
@.claude/rules/secrets-safety.md
@.claude/rules/git-safety.md
@.claude/rules/agents-safety.md
@.claude/rules/code-search.md
@.claude/rules/sdlc-gates.md
@.claude/rules/code-comments.md
@.claude/rules/engineering-conduct.md


## Code-Lessons MCP (MANDATORY PRE-IMPLEMENTATION GATE)

**HARD RULE — NON-NEGOTIABLE. NO EXCEPTIONS BEYOND THE EXPLICIT SKIP LIST BELOW.**

Before writing or modifying any non-trivial code, you MUST call the code-lessons MCP. This is a **pre-implementation gate**, not a post-hoc validation. A retroactive lesson check after the diff is already written does NOT satisfy this rule.

### Scope: every implementation task gates separately

The gate is per-implementation-task, not per-session. **Every** task that produces code edits triggers a fresh gate, including but not limited to:

- New feature implementation
- **Bug fixes** (one-line bug fixes are still bug fixes)
- **PR review feedback / "address review comments"** — each fresh batch of comments is a new round and re-runs the gate, even if you pulled lessons earlier in the same session for the previous round
- Refactors that touch logic (renames or pure formatting fall in the skip list)
- Hotfixes, follow-up edits, "while you're in there" changes
- Test additions that exercise non-trivial logic
- Migrations / schema changes (Prisma, SQL, etc.)
- Build / CI script edits that contain executable logic

Lessons pulled earlier in the session for a different task do **not** carry over. Treat each new task description (or each new round of PR feedback) as a fresh implementation gate — the diff scope is different and different lessons may apply. Reusing a prior pull is an anti-pattern.

### Required Sequence

1. **Identify scope first**: language + frameworks actually imported in the files you will touch (read `package.json` / `requirements.txt` / imports — do not assume).
2. **Skim — TWO calls, not one**: `mcp__code-lessons__list_lessons_for_stack` with the exact language + matching frameworks. Severity filtering is **EXCLUSIVE** — `severity: "high"` returns only high-tagged lessons, `severity: "medium"` returns only medium-tagged. A single call CANNOT cover both. Therefore:
   - Call 1: `severity: "high"`
   - Call 2: `severity: "medium"`
   - Add `"critical"` (Call 3) on security-sensitive paths.

   Both calls are MANDATORY on any logic change. Running only `"high"` silently drops the entire medium corpus and is a gate failure. The only time a single high-only call is acceptable is a genuinely trivial cosmetic edit (one-line CSS / hex tweak / typo-in-identifier) — and you must state that justification in the self-audit. Two skims cost ~10K tokens and are cheap insurance against missing a known mistake.
3. **Fetch**: `mcp__code-lessons__get_lessons_by_ids` for the 3–10 ids that look relevant to the diff (max 20 per call).
4. **Treat returned lessons as constraints, not suggestions** — if a lesson applies, follow it.
5. **Self-review the diff** against those lessons before declaring done.
6. **PR feedback flow**: before fixing review comments on a manager-hub PR, call `mcp__code-lessons__get_open_comments(pullRequestId)` first (uses manager-hub CUID, not GitHub PR number), AND run steps 1–3 above for the diff scope. `get_open_comments` reports what the reviewer said; the lesson skim reports what the org has already learned about that change shape — both are required.

### Scope Discipline (avoid context blow-up)

- **One call per language** when the diff spans multiple stacks (e.g. TS frontend + Python backend) — never a union call.
- Pass **only frameworks actually imported** in the touched files. Never pass every framework in `package.json` "to be safe".
- **Default coverage is `"high"` + `"medium"` (two separate calls).** Severity filtering is exclusive, so a single `"medium"` call misses high-tagged lessons. Drop to high-only when the diff is genuinely trivial (one-line cosmetic) and never below that on logic changes.
- `list_taxonomy` at most **once per session**, only if you genuinely don't know what's available.

### Anti-Patterns (will be flagged)

- ❌ Writing code, then pulling lessons "to validate" — the check must precede the edit.
- ❌ `get_lessons_by_language` or `get_lessons_for_stack` as the first call (dumps full bodies, blows context). Skim with `list_lessons_for_stack` first.
- ❌ Calling lesson tools for trivial changes outside the skip list below — wastes tokens.
- ❌ Suppressing or ignoring a returned lesson without an explicit reason recorded in the response.
- ❌ Using GitHub PR number where manager-hub CUID is required for `get_open_comments`.
- ❌ **Skipping the gate on a bug fix because "it's just a one-line fix"** — bug fixes are implementation. If it touches logic, gate it.
- ❌ **Reusing the lesson pull from earlier in the session for a new task / new round of PR feedback** — different diff, different applicable lessons, gate again.
- ❌ **Continuing implementation after `get_open_comments` without also running the skim+fetch gate** — the two MCPs answer different questions and both are required for PR feedback.
- ❌ **Running only `severity: "high"` on a logic change.** `severity` is an exclusive filter, so a single high-only call silently drops every medium-tagged lesson — that is a gate failure, not a "lighter gate". Default coverage is BOTH `"high"` and `"medium"` as two separate skim calls. High-only is reserved for the explicitly cosmetic edits called out in the skip list. If your self-audit cites only one severity on a logic change, you skipped the gate.

### Skip List (the ONLY cases where the pre-check may be omitted)

- Pure typo fixes in prose or identifiers (no logic touched).
- Comment-only edits.
- Pure whitespace / formatting changes.
- Markdown / plain-text / config / env-file edits that contain no executable code.
- Read-only investigation that produces no file edits.

If the change touches **any** executable code path beyond the skip list — including a "one-line" CSS / layout / hook / bug fix / regex tweak — the pre-check is required. When in doubt: gate it. The cost of one extra skim call is ~5K tokens; the cost of re-learning a lesson the corpus already has is a new PR comment.

### Self-Audit Before Reporting Done

When summarizing completed work, state explicitly which lessons were checked (or that the change fell into the skip list and why). **The summary MUST name both severity skims explicitly** — e.g. *"skimmed `typescript + react,recharts` at `high` AND `medium`; fetched ids X, Y; none applied / id Y applied and was followed"*. A summary that names only one severity on a logic change is itself a gate failure, even if no applicable lesson was missed — the reviewer cannot tell coverage from intent. For PR feedback rounds, state both: which `get_open_comments` findings you addressed AND which lessons you skimmed (with severities) for the new diff. If the pre-check was skipped or partial on a non-trivial change, treat it as a process failure and acknowledge it openly rather than rationalizing.