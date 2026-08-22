#!/usr/bin/env python3

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "remote-to-workspace.sh"


class RepoToClaudeTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self._write_executable(
            "curl",
            'output=""\n'
            'while [ "$#" -gt 0 ]; do\n'
            '  if [ "$1" = "-o" ]; then shift; output="$1"; fi\n'
            "  shift\n"
            "done\n"
            '[ -z "$output" ] || : > "$output"\n',
        )
        self._write_executable(
            "tar",
            'destination=""\n'
            'while [ "$#" -gt 0 ]; do\n'
            '  if [ "$1" = "-C" ]; then shift; destination="$1"; fi\n'
            "  shift\n"
            "done\n"
            'mkdir -p "$destination/rules" "$destination/agents" '
            '"$destination/scripts" "$destination/skills"\n'
            'mkdir -p "$destination/hooks/hooks"\n'
            'printf "# Base\\n" > "$destination/rules/base.md"\n'
            'printf "rules\\nagents\\nscripts\\nskills\\nHOW-TO-USE.md\\n" '
            '> "$destination/shared-manifest.txt"\n'
            'printf "# Guide\\n" > "$destination/HOW-TO-USE.md"\n'
            'printf "{}\\n" > "$destination/settings.local.json.example"\n'
            'printf "{}\\n" > "$destination/.mcp.json.example"\n'
            'printf "hook-settings\\n" > "$destination/hooks/settings.json"\n'
            'printf "#!/bin/sh\\necho block\\n" > "$destination/hooks/hooks/block-confidential.sh"\n'
            'chmod +x "$destination/hooks/hooks/block-confidential.sh"\n'
            '[ -z "${INJECT_SOURCE_SYMLINK:-}" ] || '
            'ln -s /tmp/outside "$destination/rules/linked.md"\n'
            '[ -z "${INJECT_HOOK_SYMLINK:-}" ] || '
            'ln -s /tmp/outside "$destination/hooks/hooks/linked.sh"\n'
            # When INJECT_GLOB_MANIFEST is set, add a manifest line that contains
            # a glob metacharacter to test that set -f prevents CWD expansion.
            '[ -z "${INJECT_GLOB_MANIFEST:-}" ] || '
            'printf "rules[1]\\n" >> "$destination/shared-manifest.txt"\n',
        )
        self._write_executable("gh", "printf '%040d\\n' 0\n")
        self.env = os.environ.copy()
        self.env["PATH"] = f"{self.bin}:{self.env['PATH']}"

    def tearDown(self):
        self.temporary.cleanup()

    def test_dry_run_leaves_fresh_workspace_untouched(self):
        workspace = self.root / "dry-run-workspace"
        workspace.mkdir()

        result = self._run(workspace, "--dry-run")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((workspace / ".claude").exists())
        self.assertFalse((workspace / ".mcp.json.example").exists())

    def test_apply_installs_configuration_examples_at_target_levels(self):
        workspace = self.root / "apply-workspace"
        workspace.mkdir()

        result = self._run(workspace)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((workspace / ".claude/settings.local.json.example").is_file())
        self.assertTrue((workspace / ".mcp.json.example").is_file())

    def test_apply_preserves_existing_configuration_examples(self):
        workspace = self.root / "existing-examples-workspace"
        (workspace / ".claude").mkdir(parents=True)
        settings_example = workspace / ".claude/settings.local.json.example"
        mcp_example = workspace / ".mcp.json.example"
        settings_example.write_text("local settings\n")
        mcp_example.write_text("local mcp\n")

        result = self._run(workspace)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(settings_example.read_text(), "local settings\n")
        self.assertEqual(mcp_example.read_text(), "local mcp\n")

    def test_rejects_unsafe_remote_ref(self):
        workspace = self.root / "unsafe-ref-workspace"
        workspace.mkdir()

        result = self._run(workspace, "--ref", "--upload-pack=bad")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid ref", result.stderr)
        self.assertFalse((workspace / ".claude").exists())

    def test_rejects_remote_ref_with_parent_segments(self):
        workspace = self.root / "parent-ref-workspace"
        workspace.mkdir()

        result = self._run(workspace, "--ref", "branch/../../other-repo")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid ref", result.stderr)
        self.assertFalse((workspace / ".claude").exists())

    def test_migrates_legacy_managed_block_without_losing_user_content(self):
        workspace = self.root / "legacy-marker-workspace"
        workspace.mkdir()
        (workspace / "CLAUDE.md").write_text(
            "<!-- invocare-skills:begin (managed by update-skills.sh — do not edit inside) -->\n"
            "@.claude/rules/old.md\n"
            "<!-- invocare-skills:end -->\n\n"
            "# Local guidance\n"
        )

        result = self._run(workspace)

        self.assertEqual(result.returncode, 0, result.stderr)
        content = (workspace / "CLAUDE.md").read_text()
        self.assertIn("invocare-skills:begin (managed; do not edit inside)", content)
        self.assertNotIn("managed by update-skills.sh", content)
        self.assertEqual(content.count("invocare-skills:begin"), 1)
        self.assertIn("# Local guidance", content)

    def test_preserves_user_content_when_managed_end_marker_is_missing(self):
        workspace = self.root / "missing-end-marker-workspace"
        workspace.mkdir()
        (workspace / "CLAUDE.md").write_text(
            "<!-- invocare-skills:begin (managed; do not edit inside) -->\n"
            "@.claude/rules/old.md\n"
            "# Local guidance must survive\n"
        )

        result = self._run(workspace)

        self.assertEqual(result.returncode, 0, result.stderr)
        content = (workspace / "CLAUDE.md").read_text()
        self.assertIn("# Local guidance must survive", content)
        self.assertIn("@.claude/rules/base.md", content)

        repeated = self._run(workspace, "--force")

        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        content = (workspace / "CLAUDE.md").read_text()
        self.assertIn("# Local guidance must survive", content)

    def test_tracks_remote_state_and_restores_missing_files(self):
        workspace = self.root / "state-workspace"
        workspace.mkdir()

        first = self._run(workspace)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertTrue((workspace / ".claude/.skills-sync-state").is_file())
        self.assertTrue((workspace / ".claude/.skills-sync-manifest").is_file())

        second = self._run(workspace)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("Already up to date", second.stdout)

        installed_rule = workspace / ".claude/rules/base.md"
        installed_rule.unlink()
        restored = self._run(workspace)
        self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assertTrue(installed_rule.is_file())
        self.assertIn("missing locally", restored.stdout)

        forced = self._run(workspace, "--force")
        self.assertEqual(forced.returncode, 0, forced.stderr)
        self.assertIn("Downloading latest skill set", forced.stdout)

    def test_rejects_symlinks_in_remote_payload(self):
        workspace = self.root / "symlink-workspace"
        workspace.mkdir()
        self.env["INJECT_SOURCE_SYMLINK"] = "1"

        result = self._run(workspace)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source symlink", result.stderr)

    # --- Hook installation tests ---

    def test_hooks_installed_to_dot_claude_hooks(self):
        """hooks/hooks/* must land in .claude/hooks/*, not .claude/hooks/hooks/*."""
        workspace = self.root / "hooks-install-workspace"
        workspace.mkdir()

        result = self._run(workspace)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(
            (workspace / ".claude/hooks/block-confidential.sh").is_file(),
            "hook script should be installed under .claude/hooks/",
        )
        self.assertFalse(
            (workspace / ".claude/hooks/hooks").exists(),
            "nested hooks/hooks dir must not appear under .claude/hooks/",
        )

    def test_hooks_settings_json_installed_as_reference_fragment(self):
        """hooks/settings.json must install as .claude/hooks/settings.json,
        never as .claude/settings.local.json."""
        workspace = self.root / "hooks-settings-workspace"
        workspace.mkdir()

        result = self._run(workspace)

        self.assertEqual(result.returncode, 0, result.stderr)
        fragment = workspace / ".claude/hooks/settings.json"
        self.assertTrue(fragment.is_file(), ".claude/hooks/settings.json should exist")
        self.assertEqual(fragment.read_text(), "hook-settings\n")
        self.assertFalse(
            (workspace / ".claude/settings.local.json").exists(),
            "settings.local.json must never be created by sync",
        )

    def test_dry_run_leaves_hooks_unwritten(self):
        """Dry-run must not create .claude/hooks."""
        workspace = self.root / "dry-run-hooks-workspace"
        workspace.mkdir()

        result = self._run(workspace, "--dry-run")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((workspace / ".claude/hooks").exists())

    def test_missing_hook_files_trigger_restore(self):
        """Missing installed hook files are detected and restored (like other tracked files)."""
        workspace = self.root / "restore-hooks-workspace"
        workspace.mkdir()

        first = self._run(workspace)
        self.assertEqual(first.returncode, 0, first.stderr)

        hook = workspace / ".claude/hooks/block-confidential.sh"
        self.assertTrue(hook.is_file())
        hook.unlink()

        restored = self._run(workspace)
        self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assertIn("missing locally", restored.stdout)
        self.assertTrue(hook.is_file())

    def test_hook_settings_fragment_participates_in_manifest(self):
        """hooks/settings.json installed as .claude/hooks/settings.json must appear in the manifest."""
        workspace = self.root / "hooks-manifest-workspace"
        workspace.mkdir()

        result = self._run(workspace)
        self.assertEqual(result.returncode, 0, result.stderr)

        manifest = workspace / ".claude/.skills-sync-manifest"
        self.assertTrue(manifest.is_file())
        entries = manifest.read_text()
        self.assertIn("hooks/settings.json", entries)

    def test_rejects_symlinks_in_hooks_payload(self):
        """Symlinks inside hooks/hooks/ must be rejected just like other symlinks."""
        workspace = self.root / "hooks-symlink-workspace"
        workspace.mkdir()
        self.env["INJECT_HOOK_SYMLINK"] = "1"

        result = self._run(workspace)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source symlink", result.stderr)

    def test_manifest_glob_metachar_does_not_expand_against_cwd(self):
        """Array-based manifest parsing must keep glob metacharacters literal.

        When INJECT_GLOB_MANIFEST is set, the fake tarball adds 'rules[1]' to
        shared-manifest.txt.  Because the manifest is parsed into a Bash array
        with a while-read loop (not via word-splitting of an unquoted variable),
        'rules[1]' is passed literally to the tarball lookup ($TMP/x/rules[1])
        which finds nothing and skips the item — the script still succeeds on
        the remaining valid items.  Without array parsing, 'rules[1]' would
        glob-expand against CWD and, if a matching directory existed there,
        silently install it as a sync source.
        """
        workspace = self.root / "glob-manifest-workspace"
        workspace.mkdir()
        # Create a CWD decoy that would match rules[1] if globbing were active.
        decoy = Path.cwd() / "rules1"
        decoy_created = False
        try:
            if not decoy.exists():
                decoy.mkdir()
                decoy_created = True
            self.env["INJECT_GLOB_MANIFEST"] = "1"

            result = self._run(workspace)

            # Script must succeed: valid manifest items (rules, agents …) still sync.
            self.assertEqual(result.returncode, 0, result.stderr)
            # The decoy directory must not have been treated as a sync source.
            self.assertFalse(
                (workspace / ".claude/rules1").exists(),
                "CWD 'rules1' must not be installed — glob expansion is suppressed by set -f",
            )
        finally:
            if decoy_created and decoy.exists():
                decoy.rmdir()

    def _run(self, workspace, *args):
        return subprocess.run(
            [str(SCRIPT), str(workspace), *args],
            capture_output=True,
            text=True,
            check=False,
            env=self.env,
        )

    def _write_executable(self, name, body):
        path = self.bin / name
        path.write_text(f"#!/usr/bin/env bash\nset -euo pipefail\n{body}")
        path.chmod(0o755)


if __name__ == "__main__":
    unittest.main()
