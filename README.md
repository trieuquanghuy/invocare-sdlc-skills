# InvoCare SDLC Skills

Shared Claude Code and GitHub Copilot governance for the InvoCare / FireHawk workflow: skills, rules, agents, templates, and SDLC hooks.

The repository's shared payload maps to a workspace `.claude` directory. The installer maintains the shared-rule imports in the workspace-root `CLAUDE.md` without replacing personal content.

## Quick start

### Reproducible install (recommended for production and onboarding)

Pin a published CalVer tag for a reproducible installation. Use the latest published tag — for example `v2026.08.22`:

```bash
cd <workspace>
curl -fsSL https://raw.githubusercontent.com/trieuquanghuy/invocare-sdlc-skills/main/tools/sync/remote-to-workspace.sh \
  | bash -s -- --ref v2026.08.22
```

Replace `v2026.08.22` with the latest published tag. Tags are immutable: the same ref always installs the same content.

### Current channel (updates)

Use `main` to pull the latest shared content:

```bash
cd <workspace>
curl -fsSL https://raw.githubusercontent.com/trieuquanghuy/invocare-sdlc-skills/main/tools/sync/remote-to-workspace.sh | bash
```

After installation, create untracked `.claude/settings.local.json` and `.mcp.json` files using the installed examples and values from the approved credential channel. Merge the shared hooks fragment (see [Shared hooks](#shared-hooks) below), install `jq` for the SDLC hooks, then open Claude Code and confirm `/` lists the shared skills.

## Guides

- [`SYNC.md`](SYNC.md) — all source-to-target synchronization commands and recovery
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — changing shared governance
- [`HOW-TO-USE.md`](HOW-TO-USE.md) — ticket lifecycle map

## Ownership

`shared-manifest.txt` is the synchronization allowlist. Shared content includes `rules/`, `skills/`, `agents/`, `scripts/`, and `HOW-TO-USE.md`.

These remain local and are never synchronized:

- `.claude/settings.local.json`
- workspace `.mcp.json`
- `.claude/skills/_local/`

Synchronization is one-way. Versions live in git history; published CalVer tags such as `v2026.08.22` are immutable reproducible install points.

## Shared hooks

The installer distributes hook scripts to `.claude/hooks/` and writes a reference settings fragment to `.claude/hooks/settings.json`. **Sync never overwrites your personal `.claude/settings.local.json`.**

To activate the shared hooks, manually merge the `hooks` entries from `.claude/hooks/settings.json` into your personal `.claude/settings.local.json`. A template with merge instructions is installed at `.claude/settings.local.json.example`.

Example — merging the shared hooks with a personal `sdlc-gate` hook:

```jsonc
// .claude/settings.local.json
{
  "hooks": {
    "PreToolUse": [
      // shared hooks from .claude/hooks/settings.json
      { "matcher": "Read|Grep|Glob|Bash", "hooks": [{ "type": "command", "command": ".claude/hooks/block-confidential.sh", "timeout": 5 }] },
      { "matcher": "Edit|Write|MultiEdit", "hooks": [{ "type": "command", "command": ".claude/hooks/check-lessons-fetched.sh", "timeout": 5 }] },
      // personal hook
      { "matcher": "Edit|Write|MultiEdit", "hooks": [{ "type": "command", "command": ".claude/hooks/sdlc-gate.sh", "timeout": 10 }] }
    ]
  }
}
```

If a sync run overwrites a hook script, restore it by running the same `remote-to-workspace` command (with `--ref <tag>` to pin the version) or by copying from the backup the installer creates under `.claude/.update-backup-<timestamp>`.
