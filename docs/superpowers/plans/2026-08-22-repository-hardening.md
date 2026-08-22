# Repository Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent stale generated governance, enforce safe skill invocation, distribute working hooks, and add automated repository governance and releases.

**Architecture:** Extend the existing Copilot generator with an atomic ownership manifest and opt-in pruning. Keep hook transfer explicit because repository and workspace paths differ. Enforce static repository contracts through standard-library tests and GitHub Actions, with no new runtime dependencies.

**Tech Stack:** Python 3 standard library, Bash 3.2-compatible scripts, `unittest`, GitHub Actions, GitHub CLI/API.

---

### Task 1: Generated Ownership and Safe Pruning

**Files:**
- Modify: `tools/sync/copilot/generate.py`
- Modify: `tools/sync/copilot/sync_copilot_lib.py`
- Modify: `tools/sync/remote-to-copilot.sh`
- Modify: `tools/sync/sync.sh`
- Test: `tools/sync/tests/test_workspace_to_copilot.py`
- Test: `tools/sync/tests/test_copilot_safety.py`
- Test: `tools/sync/tests/test_remote_to_copilot.py`

- [ ] **Step 1: Write failing stale-file tests**

Add tests that apply a source rule, remove it, and assert:

```python
check = self.run_sync(workspace, "--check")
self.assertNotEqual(check.returncode, 0)
self.assertIn("stale", check.stderr)
self.assertTrue(retired_destination.exists())
```

Add apply and prune assertions:

```python
apply = self.run_sync(workspace)
self.assertEqual(apply.returncode, 0)
self.assertTrue(retired_destination.exists())
self.assertIn("stale", apply.stdout)

prune = self.run_sync(workspace, "--prune")
self.assertEqual(prune.returncode, 0)
self.assertFalse(retired_destination.exists())
self.assertTrue(copilot_only_file.exists())
```

Add a dry-run test proving `--dry-run --prune` leaves both the generated file and
manifest unchanged. Add a malformed manifest test containing `../outside.md` and
assert pruning fails before writes.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tools.sync.tests.test_workspace_to_copilot \
  tools.sync.tests.test_copilot_safety \
  tools.sync.tests.test_remote_to_copilot
```

Expected: failures because `--prune`, manifest ownership, and stale reporting do
not exist.

- [ ] **Step 3: Add CLI and result types**

In `generate.py`, add:

```python
parser.add_argument(
    "--prune",
    action="store_true",
    help="remove stale files previously owned by this generator",
)
```

Reject `--check --prune`; allow `--dry-run --prune`. Pass `prune=args.prune` to
`synchronize`.

In `sync_copilot_lib.py`, add:

```python
MANIFEST_NAME = ".invocare-generated-manifest"

@dataclass(frozen=True)
class Result:
    created: int
    updated: int
    unchanged: int
    removed: int
    stale: int
    errors: tuple[str, ...]
    changes: tuple[tuple[str, str], ...] = ()
```

Update all `Result` construction and formatting sites.

- [ ] **Step 4: Implement validated manifest ownership**

Add focused helpers:

```python
def _manifest_path(github: Path) -> Path:
    return github / MANIFEST_NAME

def _relative_generated_paths(github: Path, mappings: list[Mapping]) -> set[str]:
    return {
        mapping.destination.relative_to(github).as_posix()
        for mapping in mappings
    }

def _read_manifest(github: Path) -> set[str]:
    path = _manifest_path(github)
    if not path.exists():
        return set()
    owned: set[str] = set()
    for raw in path.read_text().splitlines():
        relative = Path(raw)
        if (
            not raw
            or relative.is_absolute()
            or ".." in relative.parts
            or relative.as_posix() != raw
        ):
            raise ValueError(f"invalid generated manifest entry: {raw!r}")
        owned.add(raw)
    return owned
```

Compute `stale = previous_owned - current_owned`. In check mode, return a drift
error when stale entries exist. In apply mode, report stale files and preserve
them unless `prune=True`. Only delete regular files validated under `.github`;
reject symlinks. Remove empty parent directories up to but excluding `.github`.

Write the sorted current manifest atomically only after generated writes and
pruning complete. Dry-run and check must never write it.

- [ ] **Step 5: Forward prune safely**

Update `sync.sh` usage for Copilot routes. Update `remote-to-copilot.sh` parsing
to accept `--prune`, reject `--check --prune`, and forward it as a quoted array
element compatible with Bash 3.2.

- [ ] **Step 6: Run targeted tests**

Run the command from Step 2. Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add tools/sync/copilot tools/sync/remote-to-copilot.sh \
  tools/sync/sync.sh tools/sync/tests
git commit -m "feat(sync): track and prune stale generated files"
```

### Task 2: Hook Distribution and Dead Hook Removal

**Files:**
- Modify: `tools/sync/remote-to-workspace.sh`
- Modify: `tools/sync/workspace-to-checkout.sh`
- Modify: `hooks/settings.json`
- Modify: `settings.local.json.example`
- Test: `tools/sync/tests/test_remote_to_workspace.py`
- Test: `tools/sync/tests/test_workspace_to_checkout.py`

- [ ] **Step 1: Write failing hook mapping tests**

Extend installer fixtures with:

```python
(repo / "hooks" / "hooks").mkdir(parents=True)
(repo / "hooks" / "hooks" / "block-confidential.sh").write_text("#!/bin/bash\n")
(repo / "hooks" / "settings.json").write_text('{"hooks": {}}\n')
```

Assert apply creates `.claude/hooks/block-confidential.sh` and
`.claude/hooks/settings.json`, while preserving `.claude/settings.local.json`.
Add reverse-route coverage asserting `.claude/hooks/custom.sh` maps to
`hooks/hooks/custom.sh` without importing personal settings.

- [ ] **Step 2: Run tests to verify failure**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tools.sync.tests.test_remote_to_workspace \
  tools.sync.tests.test_workspace_to_checkout
```

Expected: hook mapping assertions fail.

- [ ] **Step 3: Implement explicit hook mapping**

After shared payload rsync in `remote-to-workspace.sh`, sync:

```bash
if [ -d "$TMP/x/hooks/hooks" ]; then
  rsync -ac --itemize-changes $DRY \
    --backup --backup-dir="$BK" \
    "$TMP/x/hooks/hooks/" "$WS/.claude/hooks/"
fi
install_example "$TMP/x/hooks/settings.json" "$WS/.claude/hooks/settings.json"
```

Create the real target directory only in apply mode. Include mapped hook files
in `.skills-sync-manifest` as `hooks/<relative-path>` entries.

In `workspace-to-checkout.sh`, sync `.claude/hooks/` into
`$CLONE/hooks/hooks/`, excluding `settings.local.json`; copy
`.claude/hooks/settings.json` to `$CLONE/hooks/settings.json` when present.

- [ ] **Step 4: Remove the dead renderer hook**

Delete the `PostToolUse` entry in `hooks/settings.json` that invokes
`.claude/scripts/render-review.js`. Keep the confidentiality and lesson gate
hooks unchanged.

Update `settings.local.json.example` to explain that
`.claude/hooks/settings.json` is the canonical shared fragment and retain the
legacy `sdlc-gate.sh` entries only if required for compatibility.

- [ ] **Step 5: Run targeted tests**

Run the command from Step 2. Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add hooks/settings.json settings.local.json.example tools/sync
git commit -m "feat(sync): distribute shared hooks"
```

### Task 3: Skill Invocation Policy

**Files:**
- Modify: `skills/create-rca/SKILL.md`
- Modify: `skills/create-spec/SKILL.md`
- Modify: `skills/pr-code-review-fixer/SKILL.md`
- Create: `tools/sync/tests/test_skill_policy.py`

- [ ] **Step 1: Write the failing policy test**

Create a standard-library frontmatter test:

```python
WRITE_CAPABLE = {
    "apply-fix",
    "create-pr",
    "create-rca",
    "create-release-report",
    "create-spec",
    "pr-code-review-fixer",
    "prepare-uat",
    "publish-rca",
    "summarize-firebase-session",
    "ticket-comment",
}

def test_write_capable_skills_disable_model_invocation(self):
    for name in WRITE_CAPABLE:
        text = (ROOT / "skills" / name / "SKILL.md").read_text()
        frontmatter = text.split("---", 2)[1]
        self.assertIn(
            "disable-model-invocation: true",
            frontmatter,
            name,
        )
```

Also assert every skill has closed frontmatter and a name matching its directory.

- [ ] **Step 2: Run the test to verify failure**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/sync/tests/test_skill_policy.py
```

Expected: failures for `create-rca`, `create-spec`, and
`pr-code-review-fixer`.

- [ ] **Step 3: Add invocation guards**

Add this frontmatter field immediately before each closing `---`:

```yaml
disable-model-invocation: true
```

- [ ] **Step 4: Run the test**

Run the command from Step 2. Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add skills/create-rca/SKILL.md skills/create-spec/SKILL.md \
  skills/pr-code-review-fixer/SKILL.md tools/sync/tests/test_skill_policy.py
git commit -m "fix(skills): guard write-capable invocation"
```

### Task 4: CI, Ownership, License, and Release Automation

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/release.yml`
- Create: `.github/CODEOWNERS`
- Create: `LICENSE`
- Create: `scripts/validate-calver.sh`
- Create: `tools/sync/tests/test_repository_policy.py`

- [ ] **Step 1: Write failing repository policy tests**

Create tests asserting:

```python
def test_ci_runs_discovery(self):
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    self.assertIn("python3 -m unittest discover", workflow)
    self.assertIn("bash -n", workflow)

def test_write_capable_release_tag_validation(self):
    accepted = subprocess.run(
        ["bash", str(ROOT / "scripts/validate-calver.sh"), "v2026.08.22"]
    )
    rejected = subprocess.run(
        ["bash", str(ROOT / "scripts/validate-calver.sh"), "latest"]
    )
    self.assertEqual(accepted.returncode, 0)
    self.assertNotEqual(rejected.returncode, 0)
```

Also assert `LICENSE`, `.github/CODEOWNERS`, and both workflows exist.

- [ ] **Step 2: Run the test to verify failure**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/sync/tests/test_repository_policy.py
```

Expected: failures because policy files do not exist.

- [ ] **Step 3: Add deterministic CalVer validation**

Create `scripts/validate-calver.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

TAG="${1:-}"
case "$TAG" in
  v[0-9][0-9][0-9][0-9].[0-1][0-9].[0-3][0-9]) ;;
  *) echo "error: tag must match vYYYY.MM.DD" >&2; exit 2 ;;
esac

python3 - "$TAG" <<'PY'
from datetime import date
import sys

year, month, day = map(int, sys.argv[1][1:].split("."))
date(year, month, day)
PY
```

Convert invalid calendar dates into a concise non-zero error.

- [ ] **Step 4: Add CI**

Create `.github/workflows/ci.yml` triggered on pull requests and pushes to
`main`, with one `quality` job on `ubuntu-latest` that checks out the repository,
sets up Python 3.12, and runs:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s tools/sync/tests -p 'test_*.py'
find hooks scripts tools/sync -type f -name '*.sh' -exec bash -n {} +
git diff --check
```

Set minimal `contents: read` permissions and concurrency cancellation.

- [ ] **Step 5: Add release workflow**

Create `.github/workflows/release.yml` with `workflow_dispatch` inputs `tag` and
optional `ref`. Give only the release job `contents: write`. Validate the tag,
checkout the requested ref, run the full test command, reject an existing remote
tag, then run:

```bash
gh release create "$TAG" --target "$GITHUB_SHA" --generate-notes
```

Use `GH_TOKEN: ${{ github.token }}`.

- [ ] **Step 6: Add ownership and license**

Create `.github/CODEOWNERS`:

```text
* @trieuquanghuy
```

Add the standard MIT license text with copyright:

```text
Copyright (c) 2026 Huy Trieu
```

- [ ] **Step 7: Run policy and full tests**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s tools/sync/tests -p 'test_*.py'
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add .github LICENSE scripts/validate-calver.sh tools/sync/tests
git commit -m "ci: enforce repository quality and releases"
```

### Task 5: Documentation and End-to-End Verification

**Files:**
- Modify: `README.md`
- Modify: `SYNC.md`
- Modify: `CONTRIBUTING.md`
- Modify: `tools/sync/README.md`

- [ ] **Step 1: Document safe pruning**

Add `--prune` to Copilot route syntax and flags. State that:

```text
--check fails for stale manifest-owned files.
--prune removes only stale files previously recorded as generated.
Copilot-only files are never inferred or removed.
```

- [ ] **Step 2: Document hook activation**

Explain that hook scripts install under `.claude/hooks/` and the shared settings
fragment installs at `.claude/hooks/settings.json`. Users merge that fragment
into personal `.claude/settings.local.json`; sync never overwrites personal
settings.

- [ ] **Step 3: Document pinned releases and complete validation**

Recommend:

```bash
curl -fsSL https://raw.githubusercontent.com/trieuquanghuy/invocare-sdlc-skills/v2026.08.22/tools/sync/remote-to-workspace.sh | bash
```

Describe `main` as the update channel. Replace individual test commands with:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s tools/sync/tests -p 'test_*.py'
```

- [ ] **Step 4: Run complete verification**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s tools/sync/tests -p 'test_*.py'
find hooks scripts tools/sync -type f -name '*.sh' -exec bash -n {} +
git diff --check
```

Expected: all tests and checks pass.

- [ ] **Step 5: Commit**

```bash
git add README.md SYNC.md CONTRIBUTING.md tools/sync/README.md
git commit -m "docs: document hardened sync and releases"
```

### Task 6: Remote Repository Enforcement

**Files:**
- No repository files

- [ ] **Step 1: Confirm CI is present on `main`**

```bash
gh workflow view ci.yml
```

Expected: the `CI` workflow exists on the default branch. Do not configure a
required check before this is true.

- [ ] **Step 2: Configure branch protection**

```bash
gh api --method PUT \
  repos/trieuquanghuy/invocare-sdlc-skills/branches/main/protection \
  -H "Accept: application/vnd.github+json" \
  --input - <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["quality"]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": true,
    "required_approving_review_count": 1
  },
  "restrictions": null,
  "required_conversation_resolution": true,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
```

Expected: the response shows `quality` as required and one approving review.

- [ ] **Step 3: Create the first immutable release**

After the hardening changes are on `main`, dispatch:

```bash
gh workflow run release.yml -f tag=v2026.08.22 -f ref=main
gh run watch --exit-status
```

Expected: release `v2026.08.22` exists and points to the tested `main` commit.

