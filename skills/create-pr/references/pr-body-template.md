## IMPORTANT RULES (remove this section before saving):
- This template is the body of the GitHub Enterprise pull request — keep it minimal
- The body MUST always begin with `Ticket: <jira-url>` — checker P7 fails the PR otherwise
- Include the data-migration checkbox ONLY when the ticket has session-log.md entries showing config/Firebase writes
- Pre-check the box `[x]` when a migration plan exists; leave `[ ]` only when work is pending
- Do not add Summary / Test Plan / Screenshots sections — the team convention is minimal bodies (per sample PRs #28 and #36)

---

# PR Body Template

## Default (code-only or no migration plan)

```
Ticket: https://invocarecompass.atlassian.net/browse/[TICKET_KEY]
```

## With Data Migration plan (config / mixed fixes)

```
Ticket: https://invocarecompass.atlassian.net/browse/[TICKET_KEY]
- [x]  Data Migration plan on UAT: Technical Approach
```

The checkbox is checked because the spec.md / session-log.md already document the migration plan; the PR is asserting that plan exists, not requesting one.

---

# PR Title Template

```
KMS-[TICKET_KEY] | [short imperative description]
```

`[TICKET_KEY]` is the full Jira ticket key including its project prefix — `GEN-XXXX`, `FIR-XXXX`, `IVC-XXXX`, `PARK-XXXX`. The `KMS-` prefix is the team convention and goes in front of every PR title.

Examples:
- `KMS-GEN-2610 | Add billedToIds into shouldTerms when search list Estimation and Invoice` (matches sample PR #36)
- `KMS-GEN-2737 | Enhance dynamic electronic signature support by refining annotation handling`
- `KMS-FIR-1952 | Fix email channel routing for templates without explicit team scope`

Rules:
- Always start with `KMS-` followed by the ticket key, then ` | `, then the description
- Capitalize the first letter of the description (sentence case)
- Keep title under 100 characters when possible — the description should describe what changed, not why
- No leading verbs like "feat:" / "fix:" — those Conventional Commits prefixes are not the team convention
