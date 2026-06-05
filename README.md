# InvoCare SDLC Skills

Shared Claude Code skill set for the InvoCare / FireHawk (Barndoor) workflow — skills, rules, subagents, and the layer-2 SDLC gate hook. This repo is the **source of truth**; `main` is always current.

> The repo root **is** the contents of a `.claude/` directory (it maps straight into a workspace's `.claude/`). The shared rules live in `.claude/rules/`; the installer generates a small managed block of `@`-imports in the **workspace-root** `CLAUDE.md` (a sibling of `.claude/`) to load them — no symlink, and your own `CLAUDE.md` content is preserved.

---

## Which guide do I need?

| You want to… | Go to | Clone? |
|---|---|---|
| **Set up from scratch** (new member) | [`ONBOARDING.md`](ONBOARDING.md) | no |
| **Install / update the skills** | [`ONBOARDING.md`](ONBOARDING.md) (steps 2 & 5) | no |
| **Change a skill and open a PR** | [`CONTRIBUTING.md`](CONTRIBUTING.md) | yes |
| **Sync workspace `.claude/` edits up into your clone** | [`CONTRIBUTING.md`](CONTRIBUTING.md) ("Sync your `.claude/` edits up into the clone") | yes |

In short: **consumers never clone** — one script (`update-skills.sh`) installs and updates, and is safe to re-run. **Contributors clone**, use `contribute-skills.sh` to push their workspace `.claude/` edits up into the clone (one way), then open PRs. The full commands live in the two guides above; this page is the map.

---

## What's shared vs personal (the fence)

`.gitignore` is the boundary. **Shared** (tracked, synced): `rules/`, `skills/` (incl. `skills/_shared/skill-pipeline-process.md`), `agents/`, `scripts/`. The workspace-root `CLAUDE.md` is **generated** by the installer from `rules/` (a managed block), not shipped or synced. **Personal / per-machine** (never tracked, never synced): `settings.local.json`, `.mcp.json`, and any personal skills you keep under `skills/_local/`.

The consumer updater honors this fence: it never writes `settings.local.json` / `.mcp.json` / `skills/_local/`, and never deletes — overwrites are backed up to `.claude/.update-backup-<timestamp>/`.

---

## Versioning & recovery

- **Version log:** git history — `git log` / `git log --oneline` is the change record (versions live in git, not a separate file).
- **Release points:** CalVer tags, e.g. `v2026.06.01`. Pin an install by running it from your workspace root with `--ref v2026.06.01` (the workspace defaults to the current directory; or pass a path explicitly: `update-skills.sh <workspace> --ref v2026.06.01`).
- **Recover from a bad update — three ways:**
  1. **Local:** restore from `.claude/.update-backup-<timestamp>/` (instant, per-machine).
  2. **Team-wide:** a contributor runs `git revert <sha>` and pushes the fix; consumers re-run `update-skills.sh`.
  3. **Whole-set rollback:** re-install with an older tag, `--ref v2026.06.01`.

---

## Notes / limitations

- The consumer sync has no `--delete`: if a shared skill is *retired* from the repo, consumers keep a stale local copy until they remove it by hand.
- The one-line `curl … | bash` install runs a remote script unreviewed. If you'd rather read before running, download `update-skills.sh` first, skim it, then run it locally — and pin a CalVer tag with `--ref v2026.06.01` (see Versioning) instead of `main` for a reproducible install.
- Plugins/marketplace were considered but can't carry the `@`-imported rules + the root-`CLAUDE.md` activation, so this clone/tarball model is used instead — it delivers the rules too.
