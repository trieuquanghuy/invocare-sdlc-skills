---
name: impact-analysis
description: >
  Produce a confidence-rated impact map of the codebase and database areas a
  Jira ticket will touch. Use this skill whenever someone says "analyze impact",
  "blast radius", "what does this ticket touch", "impact analysis on TICKET-X",
  "do impact analysis before technical approach", or any time a ticket feels
  risky and you want to understand its blast radius before writing a technical
  approach. Also trigger when the user has an existing implementation plan and
  says things like "is this plan safe", "what am I missing", or "check the
  blast radius of this plan". Over-trigger rather than under-trigger — a wasted
  run costs minutes, a missed impact costs days.
argument-hint: Jira ticket key (e.g. GEN-1234)
---

# Impact Analysis

You are producing a **confidence-rated impact map** — not an exhaustive audit.
The goal is to convert "I don't know what this touches" into a structured map
with explicit confidence ratings and explicit uncertainty markers.

**Confidence over completeness.** "I couldn't find usages" never means "no
usages exist." Say so. Over-flag uncertainty rather than under-flag it.

**Output guardian:** all output reads as written by a developer. Apply `.claude/rules/output-guardian.md` — never include tool names, skill names, session IDs, or any indication of automation in the produced document.

**Firebase safety:** apply `.claude/rules/firebase-safety.md` — this skill is read-only against Firebase. NEVER call write_rtdb / write_firestore / create_session. Every Firebase path row in the impact map must label its DB (RTDB or Firestore) explicitly; if ambiguous, query both and confirm before labelling.

**Secrets safety:** apply `.claude/rules/secrets-safety.md` — if any query, config read, or attachment surfaces a secret-looking value, redact before continuing; never paste config dumps into the impact map.

**Agent safety:** apply `.claude/rules/agents-safety.md` — the investigation fan-out (see § Sub-agent strategy) dispatches read-only subagents that inherit the rules above, receive self-contained prompts (A7), and return structured JSON (A4).

**Code search:** apply `.claude/rules/code-search.md` — reposphere is the first code-search tool; fall back to grep / rg / find only when reposphere returns empty, low-relevance, errors, or the target repo is not registered, and state the reason before falling back.

## Where this fits

This skill runs **between RCA and spec** — after `/create-rca` (`rca.md`) and
before `/create-spec` (`spec.md` + `validation.md`). It ensures the spec is
born aware of blast radius. It can also run standalone on a ticket folder where
an `rca.md` or `spec.md` already exists but the change feels risky.

## Inputs

1. **Jira ticket** — fetch via the Atlassian MCP `getJiraIssue`.
   Read the **full comment thread** — comments contain scope changes, BA
   decisions, and reproducer details that the description often lacks.
2. **Existing ticket artifacts** — read `tickets/<TICKET>/rca.md` and
   `tickets/<TICKET>/spec.md` if present. If neither exists, note it and skip
   Section 5 (Suggested Plan Edits).
3. **Code graph** — use the reposphere MCP (details below).
4. **Firebase** — use firebase-explorer MCP for Firestore/RTDB investigation
   (read-only).

## Strategic Framing (run before any tier investigation)

The biggest risk in impact analysis is spending tokens exhaustively searching
low-risk areas while skimming the area that actually breaks. This phase forces
you to think strategically about *where breakage is most likely* before
querying any tools, and to involve the user in scoping the investigation.

### Step 1 — Risk Hypothesis Brainstorm

After reading the Jira ticket (with comments), any existing plan/RCA, and the
code graph context, generate **3–5 ranked risk hypotheses** before touching
the tier analysis. Each hypothesis should:

- Name a specific breakage scenario in plain language
- Map to one or more tiers (T1–T5)
- Include a one-line rationale for why this ticket makes it likely

Think about the *nature* of the change: Is it a new field? A schema change? A
config migration? A UI-only tweak? A shared-lib update? Different change types
have predictable blast-radius patterns:

| Change type | Typically high-risk tiers |
|-------------|--------------------------|
| New field on an entity | T3 (denormalized copies), T4 (indexes, triggers) |
| Shared lib change (`fcrm-entity-manager`, `FireHawk-AuthCheck`) | T2 (callers across all repos), T5 (API consumers) |
| Firebase config change | T3 (data-coupled readers/writers), T4 (security rules, Cloud Functions) |
| Export/report pipeline change | T2 (callers), T4 (Twig templates, scheduled jobs) |
| UI-only change | T1 (direct), T2 (shared components) — lower tiers usually safe |
| API route/response shape change | T5 (contract consumers), T2 (middleware chain) |

This table is a starting heuristic, not a rule — your hypotheses should be
specific to the ticket, not generic.

### Step 2 — Assign Tier Depth

Based on your hypotheses, assign each tier an investigation depth:

- **`deep`** — Full treatment: all MCP queries, sub-agent fan-out, cross-repo
  searches. At least one tier must be `deep`.
- **`normal`** — Focused pass: 1–2 targeted queries per anchor. If signals
  emerge, escalate to `deep`.
- **`skim`** — Single broad query. If nothing surfaces, document "skimmed — no
  signals found." If something unexpected surfaces, escalate.

No tier may be skipped entirely — you always at least skim. This is the safety
net that prevents hypotheses from creating blind spots.

### Step 3 — User Checkpoint

Present your framing brief (hypotheses + tier priorities) and ask 1–2
**targeted, ticket-specific** questions. The goal is to let the user redirect
the investigation before you spend tokens.

Good checkpoint questions are specific to the ticket:
- "This touches the export pipeline — are there specific document types or
  teams you're most worried about?"
- "The field rename affects `fcrm-entity-manager` — do you know if mobile
  clients consume this field directly?"
- "I see this config is denormalized across 3 collections — is there a known
  sync mechanism, or are they manually maintained?"

Bad checkpoint questions are generic:
- "What should I focus on?"
- "Are there any areas of concern?"

If the ticket is straightforward and your hypotheses feel solid, a simple
confirmation is fine: "Does this framing look right, or should I adjust
priorities?"

**Max 2 questions.** The checkpoint should take one exchange, not become a
conversation. After the user responds, adjust your tier depths if needed and
proceed.

---

## Analysis approach: Blast-radius tiers

Explore tiers in parallel via sub-agents when available. Each tier builds on
the previous, but they can be investigated concurrently since you're searching
by different signals.

**Tier depth is driven by the Strategic Framing.** Deep tiers get the full
treatment described below. Normal tiers get a focused subset. Skim tiers get
a single broad query. See the framing phase for definitions.

### T1 — Direct (anchors)

The files and symbols the ticket actually changes. These are your **change
anchors** — everything else radiates from here.

How to find them:
- Parse the ticket description and comments for file paths, function names,
  component names, collection names, field names
- If an `rca.md` or `spec.md` exists, extract all files it identifies as
  change targets
- Use `mcp__reposphere__search_with_context` with the ticket's key concepts to
  find relevant execution flows (returns semantic hits + callers/callees)
- Use `mcp__reposphere__search_code` for lighter symbol search on the feature area

If anchors are **not findable in code** (new feature), switch to backward
search: "what code currently produces the symptom / owns the feature area?"
Use `mcp__reposphere__cross_repo_search` with the feature description as the
search query to find the owning repo, then `search_with_context` to localise.

### Mid-analysis pivot (after T1, before continuing)

Once you have your anchors, pause and sanity-check your hypotheses: **Do these
anchors match what you expected, or did something surprising show up?**

Surprises that should trigger a pivot:
- An anchor lives in a shared lib (`fcrm-entity-manager`, `FireHawk-AuthCheck`)
  that you didn't anticipate → T2 becomes `deep`
- An anchor touches a Cloud Function trigger or RTDB path you didn't know
  about → T3/T4 escalate
- The ticket description said "UI only" but anchors include an API route
  handler → T5 escalates
- Fewer anchors than expected — the feature area might be more centralized
  (or harder to find) than hypothesized

If anchors match expectations, note "Anchors matched hypotheses — no pivot
needed" and continue. If they surprise you:
1. Update your hypothesis list with the new finding
2. Reassess tier priorities (a `skim` tier might become `deep`)
3. Note the pivot briefly — this goes into Section 0 of the output

This is lightweight — a few sentences of reasoning, not a full re-framing.

### T2 — Callers and importers of T1

For each anchor symbol, find what depends on it:
- `mcp__reposphere__explore_neighborhood` on each anchor node (with `hops: 2`)
  — walks incoming callers/importers outward. Treat hop distance as the
  confidence gradient: hop 1 (WILL BREAK), hop 2 (LIKELY AFFECTED), hop 3
  (MAY NEED TESTING)
- `mcp__reposphere__graph_query` for structural "who calls X / who imports the
  module containing the anchor" questions — returns categorized incoming refs
- `mcp__reposphere__cross_repo_search` — catches usages in sibling repos that a
  single-repo neighborhood walk might miss

### T3 — Data-coupled

Code that reads or writes the affected Firestore/RTDB fields or collections.
Firestore data is often **denormalized across multiple collections** — search
by FIELD NAME, not just collection name.

- `mcp__reposphere__graph_query` — structural query for code that accesses the
  field (who reads/writes `<fieldName>` across the graph)
- `mcp__reposphere__search_with_context` / `cross_repo_search` with field names
  as queries — text+context catches accessors the graph may not edge
- `mcp__firebase-explorer__query_firestore` / `query_rtdb` on both `dev` and
  `uat` to understand the actual data shape and where the field appears.
  **Always record which DB (RTDB or Firestore) the path lives in** — the
  impact-map rows for T3/T4 carry an explicit DB column
- Check for denormalized copies: search for the field name across all
  collections, not just the "home" collection

### T4 — Config-coupled

Infrastructure and configuration that depends on the affected collections:
- **Firestore security rules** — search for collection names in rules files
  (Grep for `match /<collection>/`)
- **Composite indexes** — check `firestore.indexes.json` files
- **Cloud Functions triggers** — search for `onCreate`, `onUpdate`, `onWrite`,
  `onDelete` handlers on affected collections via
  `mcp__reposphere__search_with_context` with "trigger <collection>" or
  `mcp__reposphere__search_code` with "onCreate <collection>"
- **Scheduled jobs / cron** — search for scheduled functions that reference
  the affected data
- **Environment-driven feature flags** — search for config keys in RTDB that
  gate the affected feature

### T5 — Contract-coupled

External consumers and test coverage:
- **Existing tests** — use `mcp__reposphere__explore_neighborhood` on each
  anchor and filter the neighborhood for test files (`*.spec.*`, `*.test.*`),
  or `search_with_context` for the anchor name scoped to test paths. Test file
  **absence** is itself a signal — flag it.
- **API consumers** — if the change touches an API route handler, use
  `mcp__reposphere__cross_repo_search` on the route path / handler symbol to
  find consumers across sibling repos, and `explore_neighborhood` on the
  handler to surface the middleware chain and response-shape couplings.
- **Mobile clients** — if the change modifies an API response shape or
  Firestore document structure, mobile clients may be affected. Note this as
  an explicit uncertainty if you cannot search mobile code.

### Additional signals

Mine these alongside the tier analysis:
- **Git co-change history** — files historically changed together with anchors.
  Use `git log` on anchor files to find co-committed files.
- **Recent commits** — use `git log --since="3 months ago"` on anchor files
  to see who's been active in the area and what recent changes might interact.
- **Test coverage gaps** — test files referencing anchors (absence = signal).

## Token economy

Do not dump raw files into context. Summarize up. Caps scale with the depth
assigned during Strategic Framing:

| Tier depth | T2 symbols/anchor | T3 collections | Queries per tier |
|------------|-------------------|----------------|------------------|
| **deep**   | 10                | 5              | Unlimited (full treatment) |
| **normal** | 5                 | 3              | 1–2 targeted per anchor |
| **skim**   | —                 | —              | 1 broad query total |

- Use sub-agents for fan-out: one per repo or one per tier when available
- If you hit a token budget wall mid-analysis, emit a **partial report** with
  an explicit "stopped at tier N, did not explore further" note in the Failure
  Modes Log
- The framing phase itself is cheap — it's reasoning over information you
  already read (ticket + plan). Don't skip it to "save tokens"; it saves
  tokens downstream by preventing exhaustive searches on low-risk tiers

## Sub-agent strategy

When sub-agents are available, parallelize the investigation. This is a
**read-only parallel-investigation fan-out**, not a verification dispatch — so
dispatch the `pipeline-checker` agent type (`.claude/agents/pipeline-checker.md`),
whose tool whitelist already excludes every write-side capability, giving a
tool-level guarantee that an investigation agent cannot write to Firebase, git,
or any external system (agents-safety A2). If `pipeline-checker` is unavailable
on this platform, fall back to `Task(general-purpose)` and surface the
substitution to the user (`pipeline-checker not available, falling back to
general-purpose with prompt-level read-only guard`).

**The main thread completes the Strategic Framing phase first** (it needs the
full ticket context), then dispatches agents. Every dispatch prompt MUST be
self-contained (agents-safety A7): paste the framing brief, the tier-depth
assignments, the ticket key + environment, and the exact anchors inline — the
subagent shares no conversation context with the main thread.

Every dispatch prompt MUST carry the inheritance line (agents-safety A1):

> Apply `.claude/rules/output-guardian.md`, `.claude/rules/secrets-safety.md`,
> and `.claude/rules/code-search.md` to all output you produce. You are
> read-only: do not call any write tool (write_rtdb / write_firestore /
> create_session, git writes, gh writes, external posts, or Edit/Write outside
> a temp scratch file). Try reposphere first for code search; fall back to
> grep / rg / find only when reposphere returns empty, low-relevance, errors,
> or the target repo is not registered, and state the reason before falling back.

**Agent 1 — Code graph (T1 + T2):** Find anchors, trace callers/importers
across all repos using reposphere (`search_with_context`, `explore_neighborhood`,
`graph_query`, `cross_repo_search`). Receives the framing brief and respects
depth assignments for T2. **Reports back before Agents 2–3 finish** so the main
thread can run the mid-analysis pivot and update tier depths if needed
(re-dispatch with updated depths if pivoting).

**Agent 2 — Data layer (T3 + T4):** Investigate Firestore/RTDB fields (read-only
via firebase-explorer query tools), security rules, indexes, Cloud Function
triggers, scheduled jobs. Respects depth assignments — a `skim` T4 means one
broad query for triggers, not exhaustive search. Records the DB (RTDB /
Firestore) for every Firebase path it returns.

**Agent 3 — Contracts + history (T5 + additional signals):** Check test
coverage, API consumers, git co-change history, recent commits. Respects
depth assignments.

**Structured return (agents-safety A4).** Each agent ends its reply with a
single fenced JSON block as the LAST block, conforming to this role-specific
schema:

```json
{
  "agent": "code-graph | data-layer | contracts-history",
  "tiers": ["T1", "T2"],
  "findings": [
    {
      "location": "repo/path/file.ts:line",
      "tier": "T2",
      "db": "RTDB | Firestore | n/a",
      "reason": "why it's impacted",
      "confidence": "H | M | L",
      "evidence": "reposphere explore_neighborhood hop 1"
    }
  ],
  "blind_spots": ["what was NOT searched and why"],
  "depth_used": { "T1": "deep", "T2": "normal" }
}
```

A free-form prose reply with no JSON block is a dispatch failure: the main
thread surfaces it (`Subagent returned no JSON block — dispatch failed`) and
either re-dispatches with additional context or escalates to the user — it does
not parse the prose (agents-safety A4/A5). Per agents-safety A3, the main thread
treats every positive finding as a hypothesis to verify, not gospel: re-run the
reposphere query for any finding that materially changes the risk picture before
writing it into the impact map.

The main thread merges the structured findings into the final
`impact-analysis.md`. (Agents may stage notes in a temp scratch file, but the
authoritative hand-off is the JSON block.)

If sub-agents are not available, investigate tiers sequentially: T1 → pivot
check → T2 → T3 → T4 → T5 → additional signals.

## Output format — non-negotiable

Write a single file: `tickets/<TICKET>/impact-analysis.md`

Your output MUST use the exact 8 markdown headings (0–7) in the exact order
defined by the template. The person reading this document navigates by section
heading — if you reorganize, rename, merge, or skip sections, the document is
broken. A narrative summary or flat findings list is NOT acceptable output, no
matter how analytically strong. Structure is the product.

Read [impact-analysis-template.md](./references/impact-analysis-template.md) and
use it as your starting point. Replace the placeholder content with your
findings. Do not add, remove, or rename sections. Do not carry any
skill-name / automation attribution into the produced document header — it
reads as a developer's analysis (output-guardian).

The template's T3 and T4 tables carry an explicit **DB** column — every
Firebase path row states `RTDB` or `Firestore` (firebase-safety). Code-only
rows in those tables use `n/a`.

### Why this structure matters

The person consuming this document is a developer about to write or review a
technical approach. They need to scan section headings, jump to the tier that
concerns them, and find actionable items. A narrative essay forces them to
re-read the whole thing. The table format with H/M/L confidence lets them
triage: fix all H items, review M items, note L items.

Section 0 (Strategic Framing) is what makes the rest trustworthy — the reader
can see *why* certain tiers got deep investigation while others were skimmed,
and whether the user shaped the investigation's focus. Without it, a reader
seeing "skim depth" in the Evidence column has no way to judge whether that
was a deliberate decision or laziness.

Section 5 (Suggested Plan Edits) is the highest-leverage output — without it,
the analysis becomes a doc nobody reads. Format edits as `str_replace`-
compatible old_string/new_string blocks so they can be applied directly to the
`rca.md` / `spec.md`. Skip Section 5 only if no `rca.md` or `spec.md` exists yet.

## Edge cases

- **No plan yet** — skip Section 5, note "No spec exists yet; suggested edits
  will be generated once `/create-spec` produces one."
- **Very vague requirements** — Section 4 (BA questions) becomes the dominant
  output. Do NOT hallucinate impact for unspecified behavior. Flag the
  vagueness explicitly.
- **Anchors not findable in code (new feature)** — switch to backward search:
  find what code currently owns the feature area.
- **Token budget hit mid-analysis** — emit partial report with explicit
  "stopped at tier N" note in Section 7.

## Output Guardian Pass (before you declare done)

`tickets/<TICKET>/impact-analysis.md` is a stakeholder-facing artifact — a
developer reads it to write or review a technical approach. Re-read the file you
just saved and strip anything that violates `.claude/rules/output-guardian.md`,
because the reader has none of your workspace context and these tokens leak how
the document was produced:

- **No search / code-intelligence tool names** anywhere in the prose — not the
  call-graph tool, not the config probe, not `mcp__…`, not raw query-tool names
  outside a fenced command block. This is the easy one to miss: when the
  Coverage Statement or Failure Modes Log explains *why* a tier's confidence is
  lower, describe it in plain developer voice — "the call-graph index was
  unavailable, so caller discovery here is text-search-based and T2/T5
  confidence is lowered one notch" — NOT "the graph search returned an error so
  I fell back to grep" with the tools named. The reader cares about the coverage
  gap, not the tool that caused it.
- **No skill / slash-command names in the saved doc.** Pointers like
  `/create-spec` belong in the chat handoff below, never inside the file.
- **No session IDs, run numbers, or "AI/Claude/queried via" phrasing.**
- **No local-workspace paths** — neither bare filenames (`rca.md`, `spec.md`)
  nor paths under `tickets/…` / `.claude/…`, nor relative links. Refer to them
  in prose ("the spec", "the RCA"). Repo code paths
  (`FCRM-Web/src/forms/FormController.ts:42`) and Firebase RTDB/Firestore paths
  ARE allowed — the reader can find those.

If you find a violation and the fix is mechanical (a stray tool name, a leaked
path), rewrite it in place and re-read. The file must read as if the developer
wrote the analysis by hand.

## After writing

1. Offer the handoff: "Impact analysis complete. Ready for
   `/create-spec <TICKET>` when you are — the suggested plan edits in Section 5
   feed directly into the spec."
