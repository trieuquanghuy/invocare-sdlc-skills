# Sync Tooling

This package implements four explicit, one-way routes:

| Route | Source | Target | Implementation |
|---|---|---|---|
| `remote-to-workspace` | Published repository/ref | Workspace `.claude` | `remote-to-workspace.sh` |
| `workspace-to-checkout` | Workspace `.claude` | Local repository checkout | `workspace-to-checkout.sh` |
| `workspace-to-copilot` | Workspace `.claude` | Workspace `.github` | `copilot/generate.py` |
| `remote-to-copilot` | Published repository/ref | Workspace `.github` | `remote-to-copilot.sh` |

`sync.sh` is the public dispatcher. User-facing prerequisites, commands, expected results, and recovery steps live in [`SYNC.md`](../../SYNC.md).

## Package layout

```text
tools/sync/
  sync.sh                         public route dispatcher
  remote-to-workspace.sh         download and install shared Claude content
  workspace-to-checkout.sh       import workspace edits for contribution
  remote-to-copilot.sh           stage remote content and generate .github
  copilot/
    generate.py                   CLI and source/target resolution
    sync_copilot_discovery.py     source-file discovery and destination mapping
    sync_copilot_mapping.py       content and path translation
    sync_copilot_metadata.py      explicit agent profiles and rule-scope translation
    sync_copilot_yaml.py          shared duplicate-rejecting safe YAML parsing
    sync_copilot_native.py        native layout and higher-priority shadow checks
    sync_copilot_compatibility.py read-only JSON diagnostics and runtime limitations
    sync_copilot_validation.py    symlink, frontmatter, and link validation
    sync_copilot_lib.py           classification, atomic writes, and reporting
    requirements.txt             safe YAML parser dependency
  tests/
```

The Copilot generator supports either:

- workspace shorthand: `<workspace>/.claude` to `<workspace>/.github`; or
- explicit roots: `--source <claude-dir> --target <github-dir>`.

The explicit form powers remote staging without touching the real workspace `.claude`.

## Shared content, explicit client metadata

The target baseline is Copilot CLI 1.0.83, not a universal Claude/Copilot runtime.
Agent bodies stay in `agents/*.md`; `copilot/agents/*.yaml` supplies explicit target
metadata. Both directories travel in the selected release via `shared-manifest.txt`.
Profiles require restrictive tool declarations and an explicit model decision:
null inherits the session model; a nonempty target model ID is retained.
The four shipped profiles select capabilities per role and deliberately inherit
the session model. MCP selectors declare requirements, not server registration,
authentication, approval, or tool availability.

Metadata is source/profile-owned, never inferred from existing target frontmatter.
Unprofiled agents must use representable declarations; unsupported execution fields,
ambiguous Claude model aliases, and unknown tool identifiers fail before writes.
Profile validation does not turn shell access into a read-only permission boundary.

Rules are discovered recursively. Supported positive `paths` patterns become
`applyTo`, with brace alternatives expanded before comma joining. Unsupported scopes
are rejected rather than broadened. Global rules stay global. Independent entrypoint
imports can still load governance outside the generated instruction's scope.

## Native skill output

Copilot routes generate `skills/<name>/SKILL.md`, not `prompts/<name>.prompt.md`.
Each skill retains all visible bundled files and subdirectories, including checker
instructions, references, scripts, and binary assets. Shared resources stay under
`skills/_shared/` with their original layout, excluding per-machine runtime
`config/`. Runtime paths under `.claude/skills/_shared/config/` remain unchanged
and never become generated ownership. Markdown uses the existing
rule/agent path translations and maps `.claude/skills/` to `.github/skills/`;
source-relative links do not need flattening or compatibility aliases.
Non-Markdown files are copied unchanged. New files inherit source permissions;
existing destination permissions are preserved.

Skill metadata is parsed using a safe PyYAML loader that rejects duplicate keys.
Required names/descriptions and boolean invocation controls are validated before
writing. Metadata is preserved rather than regenerated, so manual-only skills
remain manual-only. Install the dependency with:

```bash
python3 -m pip install -r tools/sync/copilot/requirements.txt
```

The remote route checks this dependency before staging any downloaded content.
See [the migration guide](../../SYNC.md#migrating-from-generated-prompt-files) for
moving existing workspaces away from generated prompts.

## Native reuse and compatibility diagnostics

`--skills-mode mirror` remains the default, including for remote staging and central
umbrella deployment. `--skills-mode native` requires persistent adjacent `.claude`
and `.github` directories. Non-generated skill mappings point to the source files:
they participate in source/link validation but not generated ownership or writes.
Generated agents/rules keep skill references at `.claude/skills` in this mode.

Higher-priority `.github/skills` and `.agents/skills` entry points are inspected for
name shadows without following symlinks. Retiring an owned mirror requires explicit
`--prune`; unmanaged shadows always block. Reusing native project skills does not
guarantee `.claude` discovery through an umbrella added-root route or inventory
personal/global client sources.

`--compatibility-report` emits a versioned JSON object and never writes the target.
It shares the sync preflight, then reports profiles, model/tool declarations, scopes,
invocation controls, runtime references, and limitations. Its `runtime_verification`
is always `not_performed`; model/MCP availability, permissions, hooks, and actual
discovery require runtime confirmation. Configuration contents and credentials are
not read. The report returns nonzero on blocking static errors, but not merely on
unapplied generated drift or unverified runtime prerequisites.

The remote wrapper forwards report mode, sends installer progress to stderr to keep
stdout JSON clean, and rejects native mode and invalid prune combinations before
downloading. It never reuses its temporary source as a discovery directory.

## Safety invariants

- Every route is one-way and never infers or deletes destination-only files.
- `shared-manifest.txt` is the allowlist for repository/workspace transfer.
- Personal settings, local skills, sync state, and backups never enter the checkout.
- Remote workspace installation rejects unsafe source/destination paths, securely backs up type conflicts, validates and atomically replaces its tracking state, preserves malformed `CLAUDE.md` marker content, and recreates missing managed files.
- Copilot generation tracks owned files in `.github/.invocare-generated-manifest`. A normal apply reports stale manifest-owned files and retains them on disk and in the manifest. `--prune` removes only files explicitly listed in the manifest that are no longer produced by the current source; Copilot-only files not in the manifest are never touched. `--check` fails on drift or stale manifest-owned files. `--check` and `--prune` cannot be combined.
- Differing, unmanaged skill, agent, and instruction files block generation before writes. Byte-identical files can be adopted without rewriting them. Existing owned metadata is regenerated from the selected source/profile, so durable customizations must move there before migration.
- Copilot generation rejects source and destination symlinks, malformed skill metadata, broken relative resource links, and destination collisions. Stale manifest paths and their ancestors are validated before pruning.
- Source entry points must be named exactly `SKILL.md`. Native destination casing conflicts stop before writes, including on case-insensitive filesystems. Stale manifest aliases are reconciled without unlinking active files.
- Generated writes use atomic replacement; `--dry-run`, `--check`, and `--compatibility-report` write nothing to the target.
- Shell dispatch preserves argument boundaries and implementation exit codes.

## Extending the package

1. Add or change behavior in the owning implementation, not in the dispatcher.
2. Add a failing regression test before changing executable behavior.
3. Preserve the source/target vocabulary in command names and help text.
4. Update `SYNC.md` when user-visible commands, flags, or outcomes change.
5. Keep implementation details here rather than duplicating end-user scenarios.

## Validation

Run from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools/sync/tests -p 'test_*.py'
while IFS= read -r file; do
  bash -n "$file"
done < <(find hooks scripts tools/sync -type f -name '*.sh' | sort)
git diff --check
```

The suites cover routing, installation, matching-profile transport, explicit metadata,
rule scopes, local/remote reports, native reuse and shadow migration, native skill
metadata/resources, executable permissions, binary assets, ownership, idempotency,
drift reporting, prompt migration, deferred pruning, cleanup, and exit propagation.
