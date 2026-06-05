# Onboarding — InvoCare SDLC Skills (new member)

From zero to a working setup, in order. ~15 minutes. Most people only *consume* the skills and **never clone** — follow steps 1–3. Want to *change* a skill? See `CONTRIBUTING.md`. Full reference: `README.md`.

`<workspace>` below = your InvoCare umbrella checkout (the working directory that holds the `FCRM-*` / `Barndoor-*` repos).

---

## 1. Install the skills (consumer — no clone, one command)

No setup needed beyond what ships with macOS (`curl`, `tar`, `rsync`) — the installer fetches over plain https from the public repo. You just need Claude Code installed and your `<workspace>` checked out. `cd` into it, then run this once to install — re-run anytime to update, it's idempotent:
```sh
cd <workspace>
curl -fsSL https://raw.githubusercontent.com/trieuquanghuy/invocare-sdlc-skills/main/update-skills.sh | bash
```
The workspace defaults to the current directory. Add `--dry-run` to preview first (`… | bash -s -- --dry-run`) or `--ref v2026.06.01` to pin a release — when piping, flags go after `-s --`. (Prefer an explicit path? `… | bash -s -- <workspace>` still works.)

It safely adopts the shared set even if you already have a populated `.claude/` — overwrites are backed up to `.claude/.update-backup-<timestamp>/`, and your personal files are left alone. It does **not** create config files for you (step 2). For the rules, it maintains a small **managed block** of `@`-imports in your workspace-root `CLAUDE.md` (a sibling of `.claude/`): it creates the file if you don't have one, or inserts the block **above your existing content** if you do — your own `CLAUDE.md` text is never overwritten, and re-runs just refresh the block.

**What you'll see** — the installer lists only what actually changed (each `new` or `updated`, full paths), then a one-line summary:
```text
Downloading latest skill set…
Updating /path/to/workspace/.claude/ …
  new      rules/git-safety.md
  new      skills/create-rca/SKILL.md
  …
  new      skills/ticket-comment/references/short-template.md

✓ Updated .claude/ — 63 new, 0 updated.
  Left untouched: your settings.local.json, .mcp.json, and skills/_local/.
  First time? Create .claude/settings.local.json and <workspace>/.mcp.json — ask the maintainer for the config.
```
If your workspace already has its own `CLAUDE.md`, you'll see `CLAUDE.md: added the managed rules block above your existing content (kept intact)`. On later runs:
- **Nothing changed upstream** → `Already up to date: main @ <commit>` (no download).
- **You deleted a skill/file locally** → it detects the gap and re-syncs to restore it.
- **Force a full re-sync** (e.g. to undo a local edit) → add `--force`.

---

## 2. Your own config (per-machine — never shared)

The installer does **not** create these — they're per-person. Make both, then fill in your credentials:
- **`<workspace>/.claude/settings.local.json`** — permissions + the SDLC gate hook
- **`<workspace>/.mcp.json`** — your MCP server config + credentials

Get them from the maintainer (the real `.mcp.json` with your credentials), or base them on the reference templates in the repo — [`settings.local.json.example`](settings.local.json.example) and [`.mcp.json.example`](.mcp.json.example) (viewable on GitHub). Edit `<workspace>/.mcp.json` with the real server config + credentials the maintainer gave you. Both files are gitignored and never synced.

`settings.local.json` wires the **SDLC gate hook**, which uses `jq` — install it so code edits aren't disrupted:
```sh
brew install jq           # skip only if you remove the gate hook from settings.local.json
```
(`gh` is **not** needed to install or update — only for opening PRs from the terminal, see `CONTRIBUTING.md`, or as the installer's fallback if a proxy blocks the download.)

---

## 3. Verify it works

Open Claude Code in `<workspace>`, then check:
- `/` lists the skills (`create-rca`, `apply-fix`, `ticket-comment`, …).
- The rules are active (the project `CLAUDE.md` is in place and `@`-imports them).
- A read-only skill runs end-to-end — e.g. `/task-status` on a real ticket — confirming an MCP actually responds.

If all three pass, you're set up.

---

## 4. Staying up to date

Re-run the same one-command installer anytime there's an update — no clone, idempotent:
```sh
cd <workspace>
curl -fsSL https://raw.githubusercontent.com/trieuquanghuy/invocare-sdlc-skills/main/update-skills.sh | bash
```
Add `--dry-run` to preview (`… | bash -s -- --dry-run`) or pin a release with `--ref v2026.06.01`. Your `settings.local.json`, `.mcp.json`, and any personal skills under `skills/_local/` are never touched.

---

## 5. If you want to change a skill

That's the contributor path (the only one that clones): see `CONTRIBUTING.md` — clone → branch → edit → PR.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| The installer can't download / "could not download …" | Wrong `--ref` (branch or tag name), the repo's `main` has no content pushed yet, or curl is blocked by a proxy (it falls back to `gh` — `gh auth login` then re-run). The repo is public, so no access request is needed. |
| Skills don't show under `/` | `<workspace>/.claude/skills/` missing, or you didn't open Claude Code in `<workspace>`. Re-run the install one-liner (step 1). |
| A skill errors when it calls a tool | `<workspace>/.mcp.json` not set up (step 2) — get the config/creds from the maintainer. |
| An edit gets blocked by an "SDLC gate" message | Intended — the code-lessons pre-edit gate (`.claude/rules/code-lessons.md`). Ensure `jq` is installed and the hook in `settings.local.json` points at `.claude/scripts/sdlc-gate.sh`. |
| Rules don't seem to apply | Confirm `<workspace>/CLAUDE.md` exists and contains the `<!-- invocare-skills:begin -->` block of `@.claude/rules/*.md` imports. Re-run the installer to (re)generate it. |

---

## Help

- **`README.md`** — full reference (both roles, versioning, recovery).
- **`CONTRIBUTING.md`** — how to change a skill and open a PR.
- **Access / credentials** — ping the maintainer (Huy Trieu).
