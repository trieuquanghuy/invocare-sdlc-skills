# Synchronizing Skills

Use this guide to choose and run the correct source-to-target synchronization. Every route is explicit and one-way.

## Terminology

- **Remote**: the published `trieuquanghuy/invocare-sdlc-skills` repository at `main`, a branch, or a CalVer tag.
- **Workspace**: the InvoCare directory that contains local `.claude` and/or `.github` content.
- **Checkout**: a local clone of `invocare-sdlc-skills`.
- **Copilot target**: generated files under a workspace `.github`.

Examples use:

```text
<workspace>  /Users/example/Works/InvoCare
<checkout>   /Users/example/Works/InvoCare/invocare-sdlc-skills
<tag>        v2026.08.22
```

Replace `/Users/example/Works/InvoCare` with the directory that contains your `.claude` or `.github` folder.

## Choose your scenario

| You want to… | Source → target | Route |
|---|---|---|
| Install or update Claude skills | Remote → workspace `.claude` | `remote-to-workspace` |
| Bring workspace edits back for a PR | Workspace `.claude` → checkout | `workspace-to-checkout` |
| Regenerate Copilot files from local Claude files | Workspace `.claude` → workspace `.github` | `workspace-to-copilot` |
| Generate Copilot files from a published version without changing local Claude files | Remote → workspace `.github` | `remote-to-copilot` |
| Remove stale generated files from `.github` | Workspace `.claude` → workspace `.github` | `workspace-to-copilot --prune` |

## Prerequisites

| Route | Required |
|---|---|
| `remote-to-workspace` | `curl`, `tar`, `rsync`; a checkout is optional |
| `workspace-to-checkout` | A checkout and `rsync` |
| `workspace-to-copilot` | A checkout containing these tools and `python3` |
| `remote-to-copilot` | A checkout, `curl`, `tar`, `rsync`, and `python3` |

Run `./tools/sync/sync.sh help` from the checkout to list the public commands.

---

## Scenario 1: Install or update workspace `.claude`

**Use when:** setting up a workspace for the first time, pulling newer shared skills, or restoring shared files from a known release.

### Option A: Run from a checkout

1. Preview:

   ```bash
   cd <checkout>
   ./tools/sync/sync.sh remote-to-workspace <workspace> --dry-run
   ```

2. Apply:

   ```bash
   ./tools/sync/sync.sh remote-to-workspace <workspace>
   ```

3. Verify:

   ```bash
   test -d <workspace>/.claude/skills
   grep -q "invocare-skills:begin" <workspace>/CLAUDE.md
   ```

### Option B: Install without a checkout

   The shortest command uses the current directory as `<workspace>`:

   ```bash
   cd /Users/example/Works/InvoCare
   curl -fsSL https://raw.githubusercontent.com/trieuquanghuy/invocare-sdlc-skills/main/tools/sync/remote-to-workspace.sh \
     | bash -s -- --dry-run
   ```

   Run the same command without `--dry-run` to apply:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/trieuquanghuy/invocare-sdlc-skills/main/tools/sync/remote-to-workspace.sh \
     | bash
   ```

   Alternatively, stay in any directory and pass `<workspace>` explicitly:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/trieuquanghuy/invocare-sdlc-skills/main/tools/sync/remote-to-workspace.sh \
     | bash -s -- /Users/example/Works/InvoCare --dry-run
   ```

   Remove `--dry-run` to apply, and add `--ref <tag>` to pin a release:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/trieuquanghuy/invocare-sdlc-skills/main/tools/sync/remote-to-workspace.sh \
     | bash -s -- /Users/example/Works/InvoCare --ref v2026.08.22
   ```

**Result:** shared files are copied into `<workspace>/.claude`; the managed rules block in `<workspace>/CLAUDE.md` is created or refreshed. Existing personal content is preserved.

**Useful flag:** add `--force` to re-copy shared files even when the recorded remote commit is unchanged.

### Pinning a CalVer tag (reproducible installs)

For production environments and onboarding, pin a published CalVer tag so the install is reproducible. Use the latest published tag — for example `v2026.08.22`:

```bash
curl -fsSL https://raw.githubusercontent.com/trieuquanghuy/invocare-sdlc-skills/main/tools/sync/remote-to-workspace.sh \
  | bash -s -- /Users/example/Works/InvoCare --ref v2026.08.22
```

Tags are immutable: the same ref always installs the same content. `main` is the current update channel and may change between runs.

### Shared hooks after installation

The installer copies hook scripts to `<workspace>/.claude/hooks/` and writes a reference fragment to `<workspace>/.claude/hooks/settings.json`. **Sync never writes to your personal `<workspace>/.claude/settings.local.json`.**

After installation, manually merge the `hooks` entries from `.claude/hooks/settings.json` into your `.claude/settings.local.json`. A template is installed at `.claude/settings.local.json.example`. If a sync run overwrites a hook script, restore it by reinstalling the same tag or copying from `.claude/.update-backup-<timestamp>`.

---

## Scenario 2: Import workspace `.claude` changes into the checkout

**Use when:** you edited shared skills or rules in a real workspace and want those changes in the repository for review.

1. Open the checkout:

   ```bash
   cd <checkout>
   ```

2. Preview. If the checkout is directly inside the workspace, the workspace path is optional:

   ```bash
   ./tools/sync/sync.sh workspace-to-checkout --dry-run
   ```

   Otherwise pass it explicitly:

   ```bash
   ./tools/sync/sync.sh workspace-to-checkout <workspace> --dry-run
   ```

3. Apply:

   ```bash
   ./tools/sync/sync.sh workspace-to-checkout <workspace>
   ```

4. Review what entered the checkout:

   ```bash
   git status --short
   git diff --check
   ```

**Result:** allowlisted shared content is copied from `<workspace>/.claude` into the checkout. The command never deletes, commits, or pushes.

**Not copied:** personal settings, `.mcp.json`, local-only skills, sync state, backups, and repository metadata.

---

## Scenario 3: Generate `.github` from local workspace `.claude`

**Use when:** local `.claude` is the source you want Copilot to mirror.

1. Preview:

   ```bash
   cd <checkout>
   ./tools/sync/sync.sh workspace-to-copilot <workspace> --dry-run
   ```

2. Apply:

   ```bash
   ./tools/sync/sync.sh workspace-to-copilot <workspace>
   ```

3. Verify there is no generated drift:

   ```bash
   ./tools/sync/sync.sh workspace-to-copilot <workspace> --check
   ```

**Result:** source-backed files under `<workspace>/.github` are created or updated from `<workspace>/.claude`. Files that exist only in `.github` and are not recorded in `.github/.invocare-generated-manifest` are never inferred or deleted.

`--check` writes nothing. It exits `0` when generated files match and non-zero when drift or stale manifest-owned files exist. **`--check` and `--prune` cannot be combined.**

### Pruning stale generated files

A stale file is one recorded in `.github/.invocare-generated-manifest` from a previous run but no longer produced by the current source. Without `--prune`, a normal apply reports stale files but leaves them in place. With `--prune`, stale files are removed.

Preview what would be removed:

```bash
./tools/sync/sync.sh workspace-to-copilot <workspace> --dry-run --prune
```

Apply and remove stale files:

```bash
./tools/sync/sync.sh workspace-to-copilot <workspace> --prune
```

Only files explicitly listed in `.github/.invocare-generated-manifest` are eligible for removal. Files that exist only in `.github` but are not recorded in the manifest — including Copilot-only files added outside of this tooling — are never touched.

---

## Scenario 4: Generate `.github` directly from remote

**Use when:** you want Copilot content from a published branch/tag but do not want to create or modify `<workspace>/.claude`.

1. Preview:

   ```bash
   cd <checkout>
   ./tools/sync/sync.sh remote-to-copilot <workspace> --dry-run --ref <tag>
   ```

2. Apply:

   ```bash
   ./tools/sync/sync.sh remote-to-copilot <workspace> --ref <tag>
   ```

3. Verify against the same published version:

   ```bash
   ./tools/sync/sync.sh remote-to-copilot <workspace> --check --ref <tag>
   ```

Omit `--ref <tag>` to use `main`.

**Result:** remote content is downloaded into temporary staging and used to create or update `<workspace>/.github`. Temporary staging is removed on success or failure, and `<workspace>/.claude` is untouched.

### Pruning stale generated files (remote-to-copilot)

The same `--prune` semantics apply. Preview:

```bash
./tools/sync/sync.sh remote-to-copilot <workspace> --dry-run --prune --ref <tag>
```

Apply:

```bash
./tools/sync/sync.sh remote-to-copilot <workspace> --prune --ref <tag>
```

`--check --prune` is invalid for this route as well.

---

## Flags

| Flag | Routes | Meaning |
|---|---|---|
| `--dry-run` | All routes | Preview without writing to the real target |
| `--check` | Copilot routes | Write nothing; fail when generated files drift or stale manifest-owned files exist |
| `--prune` | Copilot routes | Remove files recorded in `.github/.invocare-generated-manifest` that are no longer generated |
| `--ref <branch-or-tag>` | Remote routes | Use a published branch or tag instead of `main` |
| `--force` | `remote-to-workspace` | Skip the up-to-date shortcut and restore shared files |

`--dry-run` and `--check` are mutually exclusive. `--check` and `--prune` are mutually exclusive.

## Safety and recovery

- No route infers or deletes destination-only files. Only files explicitly recorded in `.github/.invocare-generated-manifest` are eligible for pruning.
- Copilot-only files that were never recorded in the manifest are always preserved.
- Workspace installation backs up overwritten shared files under `.claude/.update-backup-<timestamp>`. Restore from the backup or reinstall with `--ref <tag>` to recover a specific version.
- Regenerate source-backed `.github` files from local `.claude` or the same remote ref.
- Copilot generation validates symlinks, frontmatter, relative links, and destination collisions before writing.
- Writes to generated files use atomic replacement.

## Troubleshooting

| Message or symptom | What to do |
|---|---|
| `workspace directory not found` | Pass an existing `<workspace>` path before flags. Quote paths containing spaces. |
| `workspace .claude not found` | Run Scenario 1 first or pass the workspace that owns the source `.claude`. |
| `python3 not found`, `rsync not found`, or `tar not found` | Install the named prerequisite and rerun the same command. |
| `invalid ref` | Use a branch/tag containing only letters, numbers, dots, underscores, slashes, or hyphens. |
| `drift detected` during `--check` | Preview, review the listed files, then run the same route without `--check`. |
| `stale generated file(s) found in manifest` during `--check` | Run the same route with `--prune` to remove or without `--prune` to leave in place. |
| `--check and --prune cannot be combined` | Use one or the other, not both. |
| Symlink, frontmatter, link, or collision error | Fix the reported source/target path; generation stops before writing. |
| Remote install says `Already up to date` but files were locally edited | Rerun `remote-to-workspace` with `--force`. |

Implementation ownership and the complete test matrix are documented in [`tools/sync/README.md`](tools/sync/README.md).
