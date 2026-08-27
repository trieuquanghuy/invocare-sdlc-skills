# Input sources

This skill processes review comments from three sources. The per-comment fix loop (Phase 1) is identical for all three; only how comments enter the loop and one Phase 0 step differ.

## Source 1 — GitHub PR

Identified by PR number, full URL, or a branch with an open PR. Fetch review threads with a read-only `gh api graphql` query for `repository.pullRequest.reviewThreads`, paginating both threads and their comments. For every comment retain `databaseId`, `path`, `line`, `originalLine`, `body`, and the parent thread's `isResolved`; ignore resolved threads unless the user explicitly selected their IDs. Refuse to process any comment without a numeric database ID, file path, and current or original line anchor. Phase 0 step 1 runs in full: `mh_list_open_prs` to find the manager-hub CUID, then `get_open_comments(pullRequestId)` to dedupe against findings already flagged upstream.

## Source 2 — Manager-hub CUID

A `c…`-prefixed identifier from manager-hub passed directly. Comment list comes from manager-hub. Phase 0 step 1 runs the same as Source 1.

## Source 3 — Local `code-review-result.json` (from the `pr-reviewer` agent)

The in-repo `pr-reviewer` subagent (defined at `.claude/agents/pr-reviewer.md`) produces a structured JSON deliverable. This skill consumes it directly — no GitHub PR or manager-hub registration required.

### Locating the JSON

- Explicit path: `./code-review-result.json`, `../some-dir/code-review-result.json`, etc.
- `auto`: look for `./code-review-result.json` in the current working directory. Error out and ask the user if it isn't there. Never crawl upward or scan unrelated directories.

### Schema reminder (from `pr-reviewer`)

```json
{
  "score": 7.5,
  "summary": "Brief overall assessment of the PR",
  "findings": [
    {
      "id": "F1",
      "severity": "critical | high | medium | low | info",
      "title": "Short finding title",
      "file": "relative/path/to/file.ts",
      "line": 24,
      "endLine": 28,
      "comment": "Detailed explanation of the issue",
      "suggestion": "Suggested fix code or approach",
      "codeContext": "the actual line(s) of code with the issue"
    }
  ],
  "stats": { "high": 1, "medium": 2, "low": 1, "info": 0 }
}
```

### Field → comment-abstraction mapping

Each `findings[]` entry becomes one review comment in the per-comment loop. The mapping is:

| JSON field | Used as | Notes |
|---|---|---|
| `id` | Comment ID (`#F1`, `#F2`, …) | Use verbatim in the final report. `--comment-ids` filter matches against this. |
| `file` | Anchored file | Path relative to repo root, as written. |
| `line` (+ `endLine` if present) | Anchored hunk | Combined with `file` to define the "anchored hunk plus enclosing function" scope from hard rule #2. |
| `title` + `comment` | Comment text used for classification | Concatenate as `"<title>\n\n<comment>"` for the bucket-classification step. |
| `codeContext` | Optional snippet for human readability in escalations | Do not parse it as authoritative — re-read the file at `file:line` before editing. |
| `severity` | **Informational only** — for prioritisation and the final report | Does NOT determine the bucket. See "Severity vs. bucket" below. |
| `suggestion` | **Advisory only** — never applied as written | See "Suggestions are advisory" below. |

### Phase 0 differences for this source

- **Step 1 — Manager-hub dedupe: SKIP.** The JSON is the canonical, already-curated finding set from the `pr-reviewer` agent. There is no manager-hub PR to query and no upstream dedupe to perform. Record `prior open review findings: N/A (input source: local JSON)` in the self-audit.
- **Step 2 — Code-lessons skim: RUNS NORMALLY.** Identify the language + frameworks of the files referenced by `findings[].file`, then call `list_lessons_for_stack` at both `high` and `medium` severities as usual. The lessons gate is about the code being edited, not where the comments came from.
- **Step 3 — Development rules: RUNS NORMALLY.** Load project-, stack-, and file-scoped rules before classifying findings or editing code.

### Suggestions are advisory

`findings[].suggestion` is prose written by the `pr-reviewer` agent. It may be wrong, out of date, or — more importantly — it may propose a *different shape of change* than this skill is allowed to make.

The rule: **read `suggestion` for context, but plan your own minimal edit from first principles using this skill's bucket / scope / line-delta constraints.** Never apply `suggestion` verbatim. Never quote it in an escalation note as if it were a proposal you endorse — that creates the same "rubber-stamp AI-written logic" failure mode the skill is explicitly designed to prevent.

If `suggestion` proposes a structural change (extract function, move to another file, change a signature), that is evidence the comment belongs in the `refactor` bucket — escalate. The suggestion's *shape* is data for classification; its *content* is not a patch you apply.

### Severity vs. bucket

`pr-reviewer` severity (`critical`…`info`) and this skill's buckets (`cosmetic`/`local_guard`/`refactor`/`behavioral`) are orthogonal axes:

- Severity = how bad the finding is if left unfixed.
- Bucket = what shape of edit is needed.

Examples:
- `critical` + `local_guard`: "missing null check on the user object — auth bypass risk" → still a local additive guard.
- `low` + `behavioral`: "nit: this should be `>=` not `>`" → still a behavioral change with an off-by-one claim.
- `info` + `refactor`: "consider splitting this 200-line function" → still escalates as a refactor.

Classify by what the comment is asking, not by its severity tag. Use severity for the final report's prioritisation order (process `critical`/`high` first within each bucket), not for the bucket decision.

### Self-audit format for this source

The Phase 0 self-audit at the top of the final report must reflect the source explicitly:

```
Policy checks:
  - input source: local JSON (./code-review-result.json) — 12 findings
  - engineering guidance reviewed: typescript+angular,rxjs@high (15), typescript+angular,rxjs@medium (9)
  - relevant guidance applied: Await asynchronous collection callbacks
  - team rules checked: FireHawk/FCRM-Web + typescript/angular + src/example.ts; applied: Keep fixes within the anchored function
  - prior open review findings: N/A (input source: local JSON)
```

### End-to-end workflow

```
1. Developer runs `/code-review` (or invokes the pr-reviewer agent) on the current branch.
   → produces ./code-review-result.json + optional HTML viewer.

2. Developer opens the HTML viewer (e.g. http://127.0.0.1:5500/code-review-result.html)
   to triage findings visually.

3. Developer runs `/pr-code-review-fixer ./code-review-result.json --dry-run`
   → skill classifies each finding into a bucket and produces the full plan + final report
     without touching any files. Developer sees what would be fixed and what would escalate.

4. Optionally: `/pr-code-review-fixer ./code-review-result.json --bucket=cosmetic`
   → apply only the cosmetic fixes first. Re-run for local_guard. Hand the rest to a human.

5. Or all at once: `/pr-code-review-fixer ./code-review-result.json`
   → run the full per-finding loop with the standard escalation rules.
```

The skill's prime directive does not relax for this source. A `pr-reviewer`-generated finding gets the same scrutiny — and the same default of escalation — as any human comment.
