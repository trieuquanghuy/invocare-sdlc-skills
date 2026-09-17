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
| Inspect static Copilot compatibility without changing the target | Local or remote source → JSON report | Either Copilot route with `--compatibility-report` |
| Reuse persistent project skills without maintaining a second copy | Adjacent workspace `.claude/skills` | `workspace-to-copilot --skills-mode native` |

## Prerequisites

| Route | Required |
|---|---|
| `remote-to-workspace` | `curl`, `tar`, `rsync`, `cksum`; a checkout is optional |
| `workspace-to-checkout` | A checkout and `rsync` |
| `workspace-to-copilot` | A checkout containing these tools, `python3`, and PyYAML |
| `remote-to-copilot` | A checkout, `curl`, `tar`, `rsync`, `cksum`, `python3`, and PyYAML |

Run `./tools/sync/sync.sh help` from the checkout to list the public commands.

For either Copilot route, install the generator's dependency into the Python environment used by `python3` (activate a virtual environment first if needed):

```bash
python3 -m pip install -r tools/sync/copilot/requirements.txt
```

PyYAML safely parses skill, rule, and agent metadata, including quoted and multiline descriptions. Both Copilot routes report a missing dependency before generating files; the remote route checks it before downloading.

The exporter targets **Copilot CLI 1.0.83**. Shared file formats do not make Claude Code, Copilot CLI, VS Code, and the cloud coding agent interchangeable. Client settings, permissions, models, hooks, MCP registration, and directory discovery still require client-specific setup. These commands do not edit personal settings or copy credentials.

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

After installation, manually merge the `hooks` entries from `.claude/hooks/settings.json` into your `.claude/settings.local.json`. A template is installed at `.claude/settings.local.json.example`. If a sync run overwrites a hook script, restore it by reinstalling the same tag or copying from `.claude/.update-backup-<timestamp>.<unique>`.

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

**Use when:** local `.claude` is the shared source you want to deploy for Copilot. Mirroring remains the default for central umbrella workspaces; native skill reuse is an explicit alternative below.

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

**Result:** native Copilot Agent Skills, instructions, and agents under `<workspace>/.github` are created or updated from `<workspace>/.claude`:

| Claude source | Copilot target |
|---|---|
| `skills/<name>/SKILL.md` | `skills/<name>/SKILL.md` |
| `skills/<name>/references/`, `scripts/`, `assets/`, and other bundled files | Same paths inside `skills/<name>/` |
| `skills/_shared/` except runtime `config/` | `skills/_shared/`, with its original subdirectories |
| `rules/<path>/<name>.md` | `instructions/<path>/<name>.instructions.md` |
| `agents/<name>.md` plus optional `copilot/agents/<name>.yaml` | `agents/<name>.md`, with explicit Copilot metadata |

Source paths in Markdown are adapted to `.github`, while relative bundle links remain intact. Non-Markdown resources are copied byte-for-byte, and new executable scripts retain their source permissions. Hidden files/directories and `skills/_local/` are excluded.

Per-machine runtime configuration under `.claude/skills/_shared/config/` stays in that location. It is not copied or claimed as generated content, and references to it are intentionally not redirected. This preserves settings created or edited by workflow runs, including Drive upload configuration.

Every skill must have a file named exactly `SKILL.md`, even on case-insensitive filesystems, with valid YAML frontmatter, a directory-matching `name` (1-64 lowercase letters, numbers, and single hyphens), and a non-empty `description` of at most 1024 characters. Existing invocation controls such as `disable-model-invocation: true` are preserved, not widened.

These are [Copilot Agent Skills](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills), not `.github/prompts/*.prompt.md` files. Copilot CLI also supports `.claude/skills` directly; this route is for maintaining a separate Copilot-adapted mirror.

Start Copilot CLI in `<workspace>` or add that workspace with `/add-dir`, then use `/skills reload`. Use `/skills info <name>` to confirm which copy is loaded when both Claude and GitHub skill directories are available.

Copilot-only files remain untouched. If an existing skill, agent, or instruction file differs from the generated content and is not in `.github/.invocare-generated-manifest`, generation stops before writing; reconcile or move that file aside first. Byte-identical files can be adopted into the manifest without rewriting them.

`--check` writes nothing. It exits `0` when generated files match and non-zero when drift or stale manifest-owned files exist. **`--check` and `--prune` cannot be combined.**

### Explicit Copilot agent profiles

Shared agent bodies remain in `.claude/agents/<name>.md`. Their Copilot metadata comes from a matching `.claude/copilot/agents/<name>.yaml` profile when present. In this repository, those source files live under `agents/` and `copilot/agents/`. The shared manifest transfers both together, so a remote release never silently borrows profiles from a different checkout version.

Example profile for `agents/reviewer.md`:

```yaml
description: Review the assigned code and report findings.
tools:
  - view
  - glob
  - reposphere/search_code
model: null
```

`tools` is an explicit restrictive agent capability list. An empty list grants no tools; an omitted list is rejected instead of accidentally granting all tools. MCP selectors use configured `server/tool` names. They do not register servers, supply credentials, or bypass permissions. In particular, granting a shell does not make shell commands read-only.

Profiles require an explicit model decision: `model: null` inherits the current Copilot session model; a nonempty Copilot model ID requests that model. All four bundled profiles deliberately inherit the session model rather than guessing a translation of Claude's `sonnet` alias. Model availability is a runtime concern.

The bundled profiles preserve each role's distinct capabilities: the PR reviewer can run shell commands and write its JSON artifact; the pipeline checker has shell/read/search access without an editor grant; the depth and breadth lenses have view/glob access without shell, editor, or Firebase tools. External MCP operations remain read-only. The three internal checker/lens profiles are not user-invocable; they remain available for coordinator dispatch.

The profiles retain the source roles' named `reposphere`, `firebase-explorer`, and `code-lesson` operations where allowed. The two Claude-specific Atlassian namespaces are explicitly bound to one Copilot server named `atlassian`; configure that server name or deliberately update the profiles to match your deployment. No generic search/lesson service is substituted for a different API contract.

Without a profile, the source agent must declare a description and an explicit, representable tool list. Unsupported tool names, Claude model aliases, malformed or duplicate YAML, and unsupported execution fields are rejected. A profile does not implement Claude-only permissions, hooks, memory, or isolation. Use genuinely client-specific authoring when those execution requirements differ.

**Migration from older generated agents:** existing target frontmatter is no longer an implicit configuration source. Move durable Copilot-specific tool/model choices into the versioned profile before regenerating manifest-owned files. Preserve any hand-authored safeguards when reconciling an unowned conflicting target; back it up outside discovery directories before moving it aside. Do not edit the ownership manifest to bypass a conflict.

### Rule scope

Rules are discovered recursively, with their relative directories preserved. Supported positive Claude `paths` patterns become Copilot `applyTo` patterns:

```yaml
---
description: Frontend rules.
paths:
  - src/frontend/**
  - tests/frontend/**/*.{ts,tsx}
---
```

This becomes `applyTo: src/frontend/**,tests/frontend/**/*.ts,tests/frontend/**/*.tsx`. Unsupported or malformed patterns fail instead of becoming global rules. Rules without `paths` remain global; the exporter does not invent narrower scopes for existing governance.

`applyTo` controls the generated instruction file, not other entry points. Existing `CLAUDE.md`, `AGENTS.md`, or Copilot instruction imports can load the same governance independently; review those imports when introducing scoped rules.

### Opt-in native skill reuse

For a project where Copilot directly discovers persistent `<workspace>/.claude/skills`, keep one skill copy:

```bash
./tools/sync/sync.sh workspace-to-copilot <workspace> --skills-mode native --dry-run
./tools/sync/sync.sh workspace-to-copilot <workspace> --skills-mode native
```

This still generates explicit agents and instructions in `.github`, but validates and reuses the shared source skills/resources without rewriting, copying, or claiming them as generated files. Skill references remain under `.claude/skills`. Native mode requires adjacent directories named `.claude` and `.github`; it cannot use an external checkout or temporary remote staging.

Copilot CLI skill precedence is `.github/skills`, then `.agents/skills`, then `.claude/skills`. Higher-priority skills with the same declared name block native reuse. Retire an existing manifest-owned mirror deliberately:

```bash
./tools/sync/sync.sh workspace-to-copilot <workspace> --skills-mode native --dry-run --prune
./tools/sync/sync.sh workspace-to-copilot <workspace> --skills-mode native --prune
```

Unmanaged shadows are never deleted, even with `--prune`; reconcile them first. Subsequent checks must include `--skills-mode native`. Omit that flag to return to mirroring. No symlinks, directory registrations, or client settings are created.

**Keep the default mirror for the umbrella workspace** when launching Copilot from child repositories and adding the umbrella root. Documented `.github` added-root discovery does not establish equivalent `.claude` added-root discovery. `COPILOT_SKILLS_DIRS` is another client-side no-copy option, but does not configure agents, rules, hooks, or MCP; this exporter does not set it. Personal/global discovery and local-only source content remain outside generated ownership.

### Read-only compatibility report

```bash
./tools/sync/sync.sh workspace-to-copilot <workspace> --compatibility-report
./tools/sync/sync.sh workspace-to-copilot <workspace> --skills-mode native --compatibility-report
```

The JSON report identifies selected agent profiles, tool/model declarations, rule scopes, skill locations and invocation controls, Claude execution extensions, declared MCP tools, referenced runtime scripts, and static conflicts. Project configuration is checked for file presence only; its contents and credentials are not read. Missing project MCP files do not imply missing servers: personal or plugin configuration may provide them.

`static_status: valid` means the exporter found no blocking static configuration or ownership errors. It is **not** an execution certification: `runtime_verification` remains `not_performed`. Confirm directory trust/discovery, model and MCP availability, approvals, and hook behavior separately. Shared Claude tool references and dynamic skill syntax are not a general-purpose runtime translation.

The Copilot exporter does not install or activate hooks/scripts. The remote route can therefore generate instructions that reference `.claude/scripts/...` without installing those files in the real workspace. Provision that runtime separately if the workflow needs it, and do not duplicate hooks already loaded from Claude settings.

The report writes no target files. It exits `0` without blocking static errors and nonzero with errors; runtime warnings alone do not make it fail. Unlike `--check`, it does not fail merely because generation has not yet been applied. Report mode is mutually exclusive with `--dry-run`, `--check`, and `--prune`.

### Migrating from generated prompt files

Older versions generated `.github/prompts/<name>.prompt.md`. The generator now creates `.github/skills/<name>/SKILL.md` instead. Existing manifest-owned prompts and their resources are reported as stale, but remain on disk **and in the manifest** until explicitly pruned. Applying once does not lose the ability to prune them later.

Preview the migration before applying. Reconcile any hand-authored native entry points, such as an `apply-fix` wrapper, without dropping their safeguards. Keep a backup outside the skill discovery directories before moving a conflicting file aside.

After generating native skills, update any Copilot-only prompts or wrappers that still depend on legacy prompt files before using `--prune`. Sync does not rewrite those Copilot-only consumers. Until legacy owned files are pruned, `--check` continues to report them as stale.

### Pruning stale generated files

A stale file is one recorded in `.github/.invocare-generated-manifest` from a previous run but no longer produced by the current source. Without `--prune`, a normal apply reports stale files but leaves them in place and retains their ownership. With `--prune`, stale files and their manifest entries are removed.

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

**Result:** remote content is downloaded into temporary staging and used to create or update native skills, instructions, and agents under `<workspace>/.github`, using the same layout and validation as Scenario 3. Temporary staging is removed on success or failure, and `<workspace>/.claude` is untouched. The selected remote ref must contain valid skill metadata and any required Copilot agent profiles.

Older refs with Claude-only agent metadata and no profiles can fail with the newer exporter. Use a source release containing matching profiles, or prepare an explicit local source/profile pair; the generator will not guess or substitute profiles from another release.

Inspect the same remote source without changing the workspace:

```bash
./tools/sync/sync.sh remote-to-copilot <workspace> --compatibility-report --ref <tag>
```

Report JSON goes to stdout and download progress to stderr. Source paths in this report refer to temporary staging, not persistent client discovery locations. Remote generation always mirrors skills; `--skills-mode native` is rejected before downloading.

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
| `--compatibility-report` | Copilot routes | Emit read-only JSON diagnostics; do not claim runtime compatibility or enforcement |
| `--skills-mode mirror\|native` | `workspace-to-copilot` | Mirror skills by default, or reuse adjacent persistent project skills; remote accepts only `mirror` |
| `--prune` | Copilot routes | Remove files recorded in `.github/.invocare-generated-manifest` that are no longer generated |
| `--ref <branch-or-tag>` | Remote routes | Use a published branch or tag instead of `main` |
| `--force` | `remote-to-workspace` | Skip the up-to-date shortcut and restore shared files |

`--dry-run`, `--check`, and `--compatibility-report` are mutually exclusive. Neither `--check` nor `--compatibility-report` can be combined with `--prune`.

## Safety and recovery

- No route infers or deletes destination-only files. Only files explicitly recorded in `.github/.invocare-generated-manifest` are eligible for pruning.
- Copilot-only files that were never recorded in the manifest are always preserved.
- Workspace installation backs up overwritten files and source/destination type conflicts under `.claude/.update-backup-<timestamp>.<unique>`. Restore from the backup or reinstall with `--ref <tag>` to recover a specific version.
- Workspace installation rejects unsafe source/destination symlinks and wrong-type write targets, preserves malformed `CLAUDE.md` marker content, and atomically repairs damaged local sync tracking instead of trusting a false up-to-date result.
- Regenerate source-backed `.github` files from local `.claude` or the same remote ref.
- Copilot generation validates symlinks, required skill metadata, relative resource links, and destination collisions before writing. Pruning validates owned paths and their ancestors before removing files.
- Native destination spelling must match the source. Case-only renames that need reconciliation stop before writes; obsolete manifest spellings are never pruned as separate files when they alias a current destination.
- Writes to generated files use atomic replacement.

## Troubleshooting

| Message or symptom | What to do |
|---|---|
| `workspace directory not found` | Pass an existing `<workspace>` path before flags. Quote paths containing spaces. |
| `workspace .claude not found` | Run Scenario 1 first or pass the workspace that owns the source `.claude`. |
| `python3 not found`, `rsync not found`, `tar not found`, or `cksum not found` | Install the named prerequisite and rerun the same command. |
| `PyYAML is required` | Activate the intended Python environment and run `python3 -m pip install -r tools/sync/copilot/requirements.txt`. |
| `invalid skill frontmatter`, `invalid skill name`, or invalid description | Fix the reported source `SKILL.md`; use valid YAML and the name/description constraints above. The generator never truncates metadata automatically. |
| `unmanaged native skill file would be overwritten` | Reconcile the existing Copilot-specific content with the source, then back up and move the conflicting file outside the skill discovery directories before rerunning. |
| `unmanaged agent` or `unmanaged rule` | Preserve local choices in an explicit source/profile or separate Copilot-only file, then reconcile the conflict. Target frontmatter is no longer an implicit override. |
| Missing/unsupported agent metadata or invalid profile | Fix the named source/profile, declare explicit tools and model policy, and use profiles from the selected release. Unsupported execution semantics are not silently dropped. |
| Unsupported rule glob | Use supported positive relative `paths` patterns; do not replace a scoped rule with `**` just to bypass the error. |
| Higher-priority skill `shadows native` | Use `--prune` only for manifest-owned mirrors; reconcile unmanaged `.github`/`.agents` shadows separately. |
| `native skills require persistent, adjacent` | Use the workspace's real `.claude` and `.github` directories, or keep mirror mode. |
| `case-only rename` | Rename the reported destination file or directory through a temporary name so its on-disk spelling matches the source, then rerun. Old manifest spellings are reconciled without deleting the active file. |
| `invalid ref` | Use a branch/tag containing only letters, numbers, dots, underscores, slashes, or hyphens. |
| `destination symlink is not allowed` | Replace the reported installer-managed symlink with a real file or directory, then rerun. |
| `destination must be a file` or `destination must be a directory` | Move the wrong-type path aside, then rerun; sync will not guess how to replace direct write targets. |
| `CLAUDE.md is not readable` | Restore read permission so sync can preserve the existing user-authored content. |
| Shared manifest validation error | Fix `shared-manifest.txt` in the selected repository ref; nested, option-like, protected, and non-canonical core entries are rejected. |
| `drift detected` during `--check` | Preview, review the listed files, then run the same route without `--check`. |
| `stale generated file(s) found in manifest` during `--check` | Run the same route with `--prune` to remove or without `--prune` to leave in place. |
| `--check and --prune cannot be combined` | Use one or the other, not both. |
| Symlink, frontmatter, link, or collision error | Fix the reported source/target path; generation stops before writing. |
| Remote install says `Already up to date` but files were locally edited | Rerun `remote-to-workspace` with `--force`. |

Implementation ownership and the complete test matrix are documented in [`tools/sync/README.md`](tools/sync/README.md).
