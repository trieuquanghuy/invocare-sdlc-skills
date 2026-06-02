# Agent Safety — How Skills Dispatch and Trust Subagents

Applies to every skill that uses the `Task` tool to dispatch a subagent. Currently: `apply-fix`, `create-rca`, `create-spec`, `create-pr`, `ticket-comment`, `publish-rca`, and any future skill that delegates work to a subagent for review, validation, or specialized analysis.

Cited from `CLAUDE.md` so all skills inherit it.

---

## A1 — Subagents inherit Output Guardian and Secrets Safety

Every dispatch prompt for a subagent MUST cite both:

- `.claude/rules/output-guardian.md` — for any output that may be surfaced to the user, copied into Jira / Confluence / a PR, or written to a shared artifact
- `.claude/rules/secrets-safety.md` — for any output that may include data read from configuration, env vars, or live systems

Subagents that produce user-visible output without inheriting these rules are non-compliant. The dispatching skill MUST surface the gap (e.g. an Output Guardian violation in a returned report) and refuse to use the output.

The dispatch prompt should include both rules in the form: `Apply .claude/rules/output-guardian.md and .claude/rules/secrets-safety.md to all output you produce.`

---

## A2 — Subagents are read-only by default

A dispatched subagent MUST NOT call write-side operations unless its specific role explicitly requires them and the dispatch prompt grants that capability:

- **git writes:** `commit`, `push`, `merge`, `reset --hard`, `branch -D`, `rebase`, `cherry-pick`, `tag`
- **gh writes:** `pr create`, `pr edit`, `pr close`, `pr merge`, `issue create`, `issue close`
- **Firebase writes:** `write_rtdb`, `write_firestore`, `create_session`, `complete_session`, `rollback_session` (subject to `firebase-safety.md`)
- **File writes outside scope:** Edit, Write, NotebookEdit on files outside the subagent's stated scope
- **External posts:** Atlassian MCP `addComment`, `createPage`, `updatePage`; Slack MCP send; any third-party write

### Tool-level enforcement: the `pipeline-checker` subagent

For verification dispatches in this project, skills MUST use the `pipeline-checker` subagent type defined in `.claude/agents/pipeline-checker.md`. It has a tool whitelist that excludes every write-side capability listed above — converting "read-only by default" from a prompt-level rule into a tool-level boundary that the harness enforces.

`Task(general-purpose)` MUST NOT be used for checker dispatches. Skills that previously dispatched `Task(general-purpose)` for verification (`apply-fix`, `create-rca`, `create-spec`, `create-pr`) have been migrated. New verification dispatches MUST follow the same pattern.

Fallback: if `pipeline-checker` is genuinely unavailable (e.g. on a platform that doesn't support custom subagents), the dispatching skill MAY fall back to `Task(general-purpose)` BUT MUST surface the substitution to the user (`pipeline-checker not available, falling back to general-purpose with prompt-level read-only guard`) so the user knows the tool-level boundary is degraded.

### Future write-capable subagents

Only the main agent (the one running the user-invoked skill) performs writes, and only after passing whatever pre-flight gate the skill defines. If a future subagent role legitimately needs write capability, that capability MUST be:

1. Documented explicitly in the dispatch prompt (e.g. "You ARE permitted to call `Edit` on files matching `tickets/{KEY}/**`")
2. Gated by a user-confirmation step in the parent skill before the subagent runs
3. Bounded — the subagent must enumerate exactly what it wrote in its return report
4. Defined as its OWN custom subagent type with the minimum tool whitelist needed — never granted via `Task(general-purpose)`

---

## A3 — Verify subagent output, don't trust it

A subagent reporting `verdict: PASS`, `Status: DONE`, `quality: PASS`, or any positive outcome is a hypothesis the main agent must verify before acting on it.

**Verification checks the dispatching skill must run after a positive subagent report:**

- If the subagent claimed to edit a file: re-read the file and confirm the edit landed
- If the subagent claimed a structural property (e.g. "5-row table present"): re-grep and confirm
- If the subagent claimed to detect a state (e.g. "no conflicts"): re-run the detection command
- If the subagent claimed an external state (e.g. "Jira ticket fetched"): confirm the data shape matches what was expected

Verification matters because subagents finish in seconds — they may have skimmed, hallucinated a check, or returned a confident report after a partial read. Treat positive reports the way you'd treat any external claim: useful, not authoritative.

---

## A4 — Subagents return structured output, not free-form prose

Every subagent dispatched from a skill returns a fenced JSON block as the LAST block of its reply, conforming to either:

- **The shared checker contract** at `.claude/skills/_shared/contracts/checker-contract.md` (for verification / validation subagents)
- **A role-specific schema** documented inline in the dispatch prompt (for non-verification roles like research, summarization, or generation)

Free-form prose responses without a structured payload are treated as a dispatch failure. The skill should:

1. Surface the absence of structured output (`Subagent returned no JSON block — dispatch failed`)
2. Apply the skill's "checker dispatch failed" branch (typically: ask the user `Proceed without verification? (yes/no)` for non-prod cases)
3. Not attempt to parse the prose

---

## A5 — Subagent failures escalate, never silently auto-retry

If a subagent returns `BLOCKED`, `NEEDS_CONTEXT`, `verdict: FAIL`, or otherwise indicates it cannot complete the task, the dispatching skill stops and surfaces the issue. It does NOT:

- Re-dispatch the same prompt with no change (wastes context, rarely produces a different result)
- Re-dispatch with a different model on a hunch (only do this when the failure mode is "this is too complex for the current model" and the user has acknowledged the cost)
- Silently downgrade the result (e.g. treat a `FAIL` as a `WARN` because there's pressure to move forward)

Valid responses to a subagent failure:

1. Provide additional context (re-read missing files, fetch additional Jira data, etc.) and re-dispatch
2. Break the task into smaller pieces and dispatch each
3. Escalate to the user with a description of what's stuck

---

## A6 — Subagents cannot dispatch other subagents

A subagent dispatched by a skill MUST NOT itself dispatch additional subagents via the `Task` tool. This prevents runaway dispatch chains, makes context budgeting predictable, and keeps the dispatching skill (the main agent) in control of the work plan.

If a subagent's task naturally decomposes (e.g. "review N files"), the dispatching skill is responsible for the decomposition: it dispatches N parallel subagents itself, not one subagent that fans out.

---

## A7 — Dispatch prompts are self-contained

Every dispatch prompt MUST contain everything the subagent needs to do its task. Subagents start with no shared conversation context — they cannot read the chat history, the user's previous messages, or files the dispatching agent has already loaded. The dispatch prompt MUST include:

- A clear statement of the role (`You are reviewing X for Y`)
- The full task description (paste it; do not link to a file the subagent has to read)
- The exact inputs (file paths AND/OR inlined content)
- The required output schema (per A4)
- The expected report format

A subagent asking the dispatching skill questions is acceptable (per the implementer-subagent prompt template), but only if the skill expects to answer them — not as a routine workaround for an under-specified prompt.

---

## A8 — Subagents do not access user secrets

Subagents inherit the same secret-handling boundary as their dispatching skill (per `secrets-safety.md`). A dispatch prompt MUST NOT include a secret value in its body — only references to where the secret lives (e.g. "the Atlassian token in `.mcp.json`").

If a subagent's task genuinely requires a secret (rare — most secrets are accessed via MCP server configuration, not by Claude reading them), the prompt names the secret by its env-var or config-file location and the subagent reads it through the same MCP that the dispatching skill would use, never via Bash `cat .env`.

---

## Scope

This rule applies to:

- All Claude Code skills in this project (`.claude/skills/**`) that dispatch subagents
- All subagent prompt templates referenced by skills (e.g. `checker-prompt.md`, `implementer-prompt.md`)
- The shared checker contract at `.claude/skills/_shared/contracts/checker-contract.md`

Individual skills may add stricter rules for their own subagents (e.g. `apply-fix` requires its pre-flight checker to be read-only with no exceptions, going beyond A2). They may NOT relax these baseline rules.
