# Pre-gates: code-review, code-lessons, and development rules

These pre-gates run **once per fix run**, not once per comment. All are mandatory before any per-comment work. Skipping one is a process failure even if the resulting fixes turn out fine.

## Gate 1 — code-review dedupe

**Applies only when the input source is a GitHub PR or a manager-hub CUID.** When the input is a local `code-review-result.json` from the `pr-reviewer` agent, skip this gate entirely and record `prior open review findings: N/A (input source: local JSON)` in the self-audit — the JSON is itself the canonical finding set. See `input-sources.md` for the source rules.

The purpose (for PR / manager-hub sources) is to find findings that an earlier review pass already flagged, so this run does not re-fix them.

```
mcp__code-review__mh_list_open_prs()
  → returns open PRs with their manager-hub CUIDs
```

Match the user's PR to a CUID. The CUID is **not** the GitHub PR number; it is a `c...`-prefixed identifier from manager-hub.

```
mcp__code-lesson__get_open_comments(pullRequestId: "<cuid>")
  → returns still-open AI-review findings for that PR
```

For each open finding returned, note its anchor and reason. When iterating comments later, if a comment matches an already-open finding (same anchor, same intent), do not re-fix it — record it as deduped in the final report.

If no manager-hub CUID exists for the PR (e.g., the PR is a draft never registered with manager-hub), skip this gate and note that in the final report. Do not invent a CUID.

## Gate 2 — code-lessons skim (MANDATORY per project CLAUDE.md)

The purpose is to surface lessons the org has already learned about the change shape you are about to make. The project CLAUDE.md mandates this; the skill restates it because PR-review-fix runs are exactly the place where lessons matter most.

### Identify scope first

Read `package.json` (or `requirements.txt`, `go.mod`, etc.) of each project touched by the PR. Only pass frameworks actually imported in the changed files. Never pass every framework in `package.json` "to be safe" — that blows context and dilutes the signal.

### Skim twice — severity is exclusive

`severity` is an exclusive filter. `severity: "high"` returns ONLY high-tagged lessons, not "high and above". A single call cannot cover two tiers.

```
Call 1 — high severity
mcp__code-lesson__list_lessons_for_stack({
  language: "typescript",
  frameworks: ["react", "recharts"],
  severity: "high"
})

Call 2 — medium severity
mcp__code-lesson__list_lessons_for_stack({
  language: "typescript",
  frameworks: ["react", "recharts"],
  severity: "medium"
})
```

Both calls are required for every fix run, including cosmetic-only runs, so the gate remains deterministic and auditable.

For security-sensitive paths (auth, payments, PII, deploy configs), add a third call with `severity: "critical"`.

### Cross-language PRs

If the PR spans multiple stacks (e.g., TS frontend + Node API + a Python script), make one pair of calls per language. Never a union call.

### Fetch the relevant ids

```
mcp__code-lesson__get_lessons_by_ids({
  ids: ["lesson-id-1", "lesson-id-2", ...]
})
```

Pick 3–10 ids that look relevant to the actual diff. Treat the returned content as constraints, not suggestions. If a returned lesson contradicts a comment's request, that is itself an escalation reason — note it.

### Anti-patterns

These will be flagged by the self-audit:

- ❌ Calling a full-body lesson retrieval endpoint first — it dumps the corpus and blows context. Skim with `list_lessons_for_stack` first.
- ❌ Reusing a skim from earlier in the session for a new fix run — different diff, different applicable lessons.
- ❌ Running only `severity: "high"` on a logic change — silently drops the entire medium-tagged corpus.
- ❌ Passing every framework in `package.json` instead of only those imported by the touched files.
- ❌ Suppressing a returned lesson without an explicit reason recorded in the response.

## Self-audit format

The pre-gate self-audit must appear at the top of the final report. It is part of how the skill proves it ran correctly.

```
Policy checks:
  - engineering guidance reviewed: typescript+react,recharts@high (12), typescript+react,recharts@medium (8)
  - relevant guidance applied: Async collection callbacks must be awaited
  - team rules checked: FireHawk/FCRM-Web + typescript/react + src/example.ts; applied: Keep fixes within the anchored function
  - prior open review findings: 4 (deduped 1 against this run)
```

A summary that names only one severity on a logic change is itself a gate failure, even if no applicable lesson was missed — the reviewer cannot tell coverage from intent.

## Gate 3 — development rules

After language/framework discovery and before classifying any finding or editing code, call:

```text
get_development_rules({
  project: "<owner/repo>",
  language: "<detected language>",
  frameworks: ["<actually imported frameworks>"],
  filePath: "<target file>"
})
```

Treat returned rules as binding. On conflicts, the more-specific rule wins. Record the scope and every applied rule in the self-audit; if a rule conflicts with the requested fix, escalate instead of overriding it.
