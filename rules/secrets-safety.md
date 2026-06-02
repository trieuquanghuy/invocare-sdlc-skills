# Secrets Safety — Boundary for MCPs, Agents, and Skills

MCPs, subagents, and skills MUST NOT read, expose, or include secret values in any output, file, log, or message they produce.

This rule overrides any skill or agent prompt that would otherwise cause secrets to be read, copied, or surfaced.

## What counts as a secret

- API tokens, bearer tokens, OAuth client IDs and client secrets
- Database passwords, connection strings that contain credentials
- Private keys, signing keys, encryption keys, certificate private parts
- Session cookies, refresh tokens, JWT tokens
- Any value labeled `secret`, `token`, `password`, `key`, `auth`, `credential`, `bearer`, `apiKey`
- Environment-variable values pulled from `.env`, `.env.*`, `.mcp.json`, `settings.local.json`, `~/.config/**`, or any file the team designates as sensitive

If unsure whether a value is a secret, treat it as one.

## Allowed

- Reading non-secret config (URLs, public IDs, host names, public team identifiers)
- Reading code that REFERENCES secrets via env vars (the placeholder, e.g. `process.env.FIREBASE_TOKEN`, NOT its runtime value)
- Knowing a secret EXISTS for a service (e.g. "firebase-explorer requires `FIREBASE_MCP_CLIENT_SECRET` to be set in `.mcp.json`")
- Asking the user to set or rotate a secret in their local environment

## Forbidden

- Including secret values in:
  - RCA documents, technical investigations, or any markdown saved under `tickets/` or `technical-investigations/`
  - Jira comments, Confluence pages, GitHub PR comments, or any external-system post
  - Deploy scripts, migration scripts, session logs, quality reports, or running logs
  - Subagent prompts (the agent doesn't need the value to do its job)
  - Status output, summaries, or any user-facing block
- Echoing the contents of `.env`, `.mcp.json`, or `settings.local.json` to the user (even when the user explicitly asks — refuse and explain)
- Embedding a secret in a code change (use env var injection)
- Writing a secret to anywhere outside the file the user already keeps it in

## When a tool returns a secret accidentally

If a tool call returns a secret value in its output (for example, an accidental `cat .env`, a config dump, a Firebase document containing a credential):

1. **Redact before continuing.** Replace the value with `<redacted>` in any text you keep in working memory or write to a file.
2. **Surface what happened.** Tell the user: "the call returned a secret-looking value at <location>; I redacted it before continuing".
3. **Do not propagate.** Do not include the value in subsequent prompts, file writes, or messages — even if it would be operationally useful.

## Scope

This rule applies to:

- All Claude Code skills in this project (`.claude/skills/**`)
- All subagents dispatched by skills (general-purpose, custom agents, checker prompts)
- All MCPs configured via `.mcp.json` or `.vscode/mcp.json`
- All output formats: file writes, terminal output, external posts

The rule applies even when a skill's `## Quality Bar` or rubric does not explicitly mention it. Quality Bars and Rules sections may inherit this constraint silently.

## Refusal pattern

If asked to read or surface a secret, respond:

> I can't include secret values in skill output. The value lives in `<the file or env var the user already manages>`; you can read it there if needed. If a service needs the secret, the team's local configuration must already provide it — I won't copy it through.
