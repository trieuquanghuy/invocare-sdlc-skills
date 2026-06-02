# Code Search — Reposphere First, Grep as Fallback

Applies to every code-search action performed in this project, whether by the main agent or any dispatched subagent (`Agent` / `Task` tool, including the `Explore` agent and `general-purpose` agent). Cited from `CLAUDE.md` so all skills and agents inherit it.

The goal is to leverage the project's repository intelligence (reposphere MCP) — which understands symbols, imports, call graphs, and cross-repo relationships — instead of falling straight to text-pattern tools (`grep` / `rg` / `find`) that miss structural context and waste tokens on noisy hits.

---

## C1 — Reposphere is the default code-search tool

When the task requires locating code — a symbol, function, type, file, usage, definition, or any "where is X" question — the FIRST attempt MUST use the reposphere MCP.

Preferred tools, in order of usefulness:

- `mcp__reposphere__search_with_context` — best general-purpose code search; returns hits with surrounding context
- `mcp__reposphere__search_code` — lighter text/symbol search across the indexed repo
- `mcp__reposphere__cross_repo_search` — when the answer may live in a sibling repo (FCRM-Web, manager-hub, etc.)
- `mcp__reposphere__explore_neighborhood` — once a seed entity is known, walk its imports / callers / callees
- `mcp__reposphere__graph_query` — for structural questions (who calls X, what imports Y)
- `mcp__reposphere__get_review_context` — when investigating a PR diff

Tools like `Grep` (ripgrep), `Bash` with `grep` / `rg` / `find`, and the `Explore` agent's default grep behavior MUST NOT be the first attempt.

---

## C2 — Fallback to grep is allowed only when reposphere is genuinely unhelpful

After the reposphere attempt, fallback to `Grep` / `Bash rg` / `find` / spawning an `Explore` agent with grep is permitted ONLY when one of the following is true:

1. **Empty results** — reposphere returns zero hits for a query that is known (or strongly believed) to exist in the codebase.
2. **Low-relevance results** — the hits returned do not match the query intent (e.g. the agent asked for a config key and got unrelated type definitions).
3. **Target repo not registered** — `mcp__reposphere__list_repos` shows the repository you need to search has not been indexed.
4. **Tool error** — the MCP returns an error, times out, or is unavailable.

Before switching, the agent MUST state the reason in one line of user-visible text, e.g.:

> reposphere `search_with_context` returned 0 hits for `useBrandFilter`; falling back to `grep`.

A silent fallback (running grep without surfacing the reposphere miss) is a rule violation, because it hides whether the index is stale or the query was poorly framed — both of which are useful signals.

---

## C3 — Subagent dispatches inherit this rule

When the main agent dispatches a subagent for any task that may involve code search (`Explore`, `general-purpose`, `gsd-*` agents, `pipeline-checker`, or any future agent), the dispatch prompt MUST include the instruction:

> Apply `.claude/rules/code-search.md` to all code-search steps. Try reposphere first (`mcp__reposphere__search_with_context` or a more specific tool); fall back to `grep` / `rg` / `find` only when reposphere returns empty, low-relevance, errored, or the target repo is not registered, and state the reason before falling back.

This matches how `agents-safety.md` extends `output-guardian.md` and `secrets-safety.md` to subagents: the rule binds the dispatcher, who is responsible for binding the dispatched agent.

The `Explore` agent in particular is a heavy grep user; its dispatch prompt MUST carry this instruction or its results are treated as un-vetted.

---

## C4 — Skip List (when reposphere may be omitted)

The rule does NOT apply to:

- **Filename lookups when the absolute path is already known** — `Read` on a known path goes straight to `Read`, no search needed.
- **Configuration / data file inspection** — `cat`-equivalent reads of `package.json`, `.mcp.json`, `tsconfig.json`, etc. via `Read`.
- **Local-only scratch / working directory exploration** — `ls`, `git status`, `git diff` on the current repo state.
- **Local files outside any registered repo** — `tickets/`, `.planning/`, session logs, RCA drafts, anything under the user's workspace that reposphere does not index.
- **Git-history searches** — `git log`, `git blame`, `git grep` against history are not covered (reposphere indexes the current tree, not commit history).
- **Tool-specific text checks** — looking for a string inside an MCP response, a JSON blob already loaded into the conversation, or another in-memory artifact.

When in doubt, try reposphere first. The cost of one extra MCP call is small; the cost of grepping a 200K-LOC monorepo and dumping the results into context is large.

---

## C5 — Anti-Patterns (will be flagged)

- ❌ Reaching for `Grep` / `rg` / `Bash find` as the first action on a code-search task.
- ❌ Dispatching the `Explore` agent without including the `code-search.md` instruction in the prompt.
- ❌ Falling back from reposphere to grep silently, with no one-line reason surfaced.
- ❌ Treating a reposphere "empty result" as gospel without considering that the query may have been wrong (rephrase / try a different reposphere tool before giving up).
- ❌ Running grep "in parallel just to compare" — pick reposphere first, only escalate when it fails.
- ❌ Falling back to grep over the local repo when the answer was likely in a sibling repo — try `cross_repo_search` before grep.

---

## Scope

This rule applies to:

- All Claude Code skills in this project (`.claude/skills/**`)
- All subagents dispatched by skills (`Explore`, `general-purpose`, `gsd-*`, `pipeline-checker`, etc.)
- All code-search tool calls: `Grep`, `Bash` (`grep`/`rg`/`find`), and the reposphere MCP

Individual skills may add stricter conventions (e.g. always start with `cross_repo_search` because their work spans multiple repos). They MAY NOT relax this baseline.
