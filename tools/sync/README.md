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
    sync_copilot_validation.py    symlink, frontmatter, and link validation
    sync_copilot_lib.py           classification, atomic writes, and reporting
  tests/
```

The Copilot generator supports either:

- workspace shorthand: `<workspace>/.claude` to `<workspace>/.github`; or
- explicit roots: `--source <claude-dir> --target <github-dir>`.

The explicit form powers remote staging without touching the real workspace `.claude`.

## Safety invariants

- Every route is one-way and never infers or deletes destination-only files.
- `shared-manifest.txt` is the allowlist for repository/workspace transfer.
- Personal settings, local skills, sync state, and backups never enter the checkout.
- Copilot generation tracks owned files in `.github/.invocare-generated-manifest`. A normal apply reports stale manifest-owned files but leaves them in place. `--prune` removes only files explicitly listed in the manifest that are no longer produced by the current source; Copilot-only files not in the manifest are never touched. `--check` fails on drift or stale manifest-owned files. `--check` and `--prune` cannot be combined.
- Copilot generation rejects source and destination symlinks, malformed frontmatter, broken relative links, and destination collisions.
- Generated writes use atomic replacement; `--dry-run` and `--check` write nothing.
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
bash -n tools/sync/*.sh
git diff --check
```

The suites cover routing, installation, direct remote staging, local Copilot generation, safety checks, idempotency, drift reporting, pruning, cleanup, and exit propagation.
