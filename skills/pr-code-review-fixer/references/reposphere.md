# Reposphere playbook for code-graph + cross-repo impact

Reposphere is the repository-intelligence layer for this skill — it answers both the **single-repo** questions ("who calls this symbol", "what's the blast radius of this refactor") and the **cross-repo** questions ("does any sibling repo import this"). It is the tool `.claude/rules/code-search.md` C1 mandates: try reposphere first, fall back to `grep` / `rg` only when it returns empty, low-relevance, errored, or the target repo isn't registered — and state the reason before falling back.

For PR-review-fix work, reposphere is used in two shapes of edit:

1. **Caller/callee evidence within one repo** — verifying cross-file rules (b)/(c) and producing refactor-escalation blast-radius notes (see "Caller/callee evidence (single repo)" below).
2. **Cross-repo impact** — changes to a shared library or any symbol that could plausibly be imported by another project. The InvoCare workspace ships two npm-published shared libs (`fcrm-entity-manager` / `@firehawk/fcrm-entity-manager`, `FireHawk-AuthCheck` / `@FireHawk/firehawk-authcheck`) used by many backend services. They are **not workspace-linked** — consumers must bump dep versions explicitly.

## Caller/callee evidence (single repo)

Use these for the cross-file rules and refactor escalations. The relevant tools:

| Question this run needs to answer | Tool |
|---|---|
| "Who exactly calls this function?" (inbound edges) | `mcp__reposphere__graph_query` (callers-of query) or `mcp__reposphere__explore_neighborhood` |
| "How big is the blast radius of this symbol?" (callers/callees, affected flows) | `mcp__reposphere__explore_neighborhood` |
| "What does this PR diff actually touch?" | `mcp__reposphere__get_review_context` |
| "Find this symbol / string with surrounding context" | `mcp__reposphere__search_with_context`, `mcp__reposphere__search_code` |

### Verifying cross-file rule (b): "exactly one caller, the anchored site"

```
mcp__reposphere__explore_neighborhood({ entity: "<callee-function-name>" })
```

(or an explicit callers-of query via `mcp__reposphere__graph_query`). Inspect the inbound callers. Rule (b) is satisfied **only when**:

- exactly one inbound caller is listed, AND
- that caller's location matches the anchored site of the review comment.

If the result shows more than one caller, the rule is not satisfied — escalate. If the repo isn't indexed (not in `mcp__reposphere__list_repos`, or the query returns empty for a symbol known to exist), the rule is unavailable — escalate.

### Verifying cross-file rule (c): "provably additive"

```
mcp__reposphere__graph_query({ ... })   // enumerate callers of the symbol
// or: mcp__reposphere__explore_neighborhood({ entity: "<callee-function-name>" })
```

Enumerate every caller in the result. For an additive change (new optional parameter, widened return type, new overload), each caller must continue to compile and behave identically without modification. If you cannot confirm that for every caller — escalate.

### Producing the escalation note for a `refactor` comment

```
mcp__reposphere__explore_neighborhood({ entity: "<anchored-symbol>" })
mcp__reposphere__get_review_context({ ... })   // the PR diff's touched flows
```

Use the caller count and the affected-process list in the escalation note. A human reviewer decides much faster when they see "7 callers across 3 files, affects CheckoutFlow and RefundFlow" than when they see "this is a refactor."

### Repo not indexed

If reposphere has no data for the repo (`mcp__reposphere__list_repos` doesn't list it, or a neighborhood/graph query returns empty for a symbol you know exists):

1. The project may not be registered yet — reposphere is the indexer.
2. **Do not silently proceed without the data.** Cross-file rules (b) and (c) become unavailable; behave as if those clauses do not exist for the affected comments and escalate.
3. Per `code-search.md` C2, you may fall back to `grep` / `rg` to confirm a caller set only after stating the reason the reposphere query was unhelpful.

## When to run a cross-repo check

Run a reposphere check for any of these comment scenarios:

- A change to `fcrm-entity-manager` or `FireHawk-AuthCheck` (hard rule #9 already escalates these, but include the cross-repo data in the escalation note).
- A signature change to an exported function in any utility package that other repos might consume.
- Removing or renaming a public API in a service whose name pattern (`FCRM-*-API`, `Barndoor-*-App`) suggests other services call it.
- Schema or template changes in `document-templates/` (consumed by Reports/Cloud-Functions).

If the change is purely internal to one app's UI or to a script that has no exports, you can skip the cross-repo check — the single-repo caller/callee evidence above is sufficient.

## Tools and what they answer

| Question | Tool |
|---|---|
| "Does any sibling repo reference this symbol?" | `mcp__reposphere__cross_repo_search` |
| "Show me the call sites with surrounding context" | `mcp__reposphere__search_with_context` |
| "What's the neighborhood around this entity across repos?" | `mcp__reposphere__explore_neighborhood` |
| "Which repos are registered and analyzed?" | `mcp__reposphere__list_repos` |
| "Is this symbol part of dead code anywhere?" | `mcp__reposphere__find_dead_code` |

## Required-research patterns

### Shared-lib edit escalation

For any change anchored in `fcrm-entity-manager` or `FireHawk-AuthCheck`:

```
mcp__reposphere__cross_repo_search({
  query: "<exported-symbol-name>",
  // optionally narrow to relevant orgs / repo patterns
})
```

Include the matching-repo count and any high-traffic consumer (e.g., `FCRM-Cloud-App`) in the escalation note. This tells the human how many consumer-side dep bumps will follow. Hard rule #9 makes the escalation mandatory; the reposphere data makes the escalation actionable.

### Signature change in a service that might be called by siblings

```
mcp__reposphere__cross_repo_search({
  query: "<function-name-or-route-path>"
})
```

If the symbol appears in another repo, treat the cross-file rule (b) / (c) analysis as failed for the cross-repo dimension and escalate. The other repo's tests will not be run by this skill's verification step, so silent breakage there is invisible.

## Repo registration

Reposphere only finds matches in repos it has registered. Before relying on a "no cross-repo references" result, sanity-check:

```
mcp__reposphere__list_repos()
```

If the workspace siblings aren't registered, a clean `cross_repo_search` is not evidence of safety. In that case, fall back to treating the edit as if cross-repo callers exist and escalate.

## When reposphere does NOT help

- **Behavior driven by Firebase config.** Reposphere indexes code, not Firestore documents. Use `firebase-explorer`.
- **Runtime composition** (e.g., services that publish to a queue consumed by another service). Reposphere will not catch a `pubsub` topic name that links two repos through message passing — that pattern is invisible to static graph indexing. If a comment touches a service boundary defined by a queue / event / cron, escalate with that note.
