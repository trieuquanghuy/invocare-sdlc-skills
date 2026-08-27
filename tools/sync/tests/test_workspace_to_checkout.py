#!/usr/bin/env python3

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SYNC_DIR = Path(__file__).resolve().parents[1]


class WorkspaceToCheckoutTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.workspace = self.root / "workspace"
        self.checkout = self.root / "checkout"
        self.sync = self.checkout / "tools/sync"
        self.sync.mkdir(parents=True)
        (self.checkout / "skills").mkdir()
        (self.checkout / "hooks").mkdir()
        (self.checkout / "hooks/hooks").mkdir()
        (self.checkout / "shared-manifest.txt").write_text("skills\n")
        shutil.copy2(SYNC_DIR / "workspace-to-checkout.sh", self.sync)
        shutil.copy2(SYNC_DIR / "remote-to-workspace.sh", self.sync)

    def tearDown(self):
        self.temporary.cleanup()

    def test_rejects_source_symlinks(self):
        references = self.workspace / ".claude/skills/demo/references"
        references.mkdir(parents=True)
        outside = self.root / "outside.md"
        outside.write_text("private\n")
        (references / "linked.md").symlink_to(outside)

        result = self._run()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source symlink", result.stderr)
        self.assertFalse(
            (self.checkout / "skills/demo/references/linked.md").exists()
        )

    def test_copies_nested_reference_files_with_common_names(self):
        references = self.workspace / ".claude/skills/demo/references"
        references.mkdir(parents=True)
        (references / "README.md").write_text("reference guide\n")
        (references / "request.example").write_text("example body\n")

        result = self._run()

        self.assertEqual(result.returncode, 0, result.stderr)
        copied = self.checkout / "skills/demo/references"
        self.assertEqual((copied / "README.md").read_text(), "reference guide\n")
        self.assertEqual((copied / "request.example").read_text(), "example body\n")

    def test_reports_empty_manifest(self):
        (self.checkout / "shared-manifest.txt").write_text("# no shared files\n")
        (self.workspace / ".claude").mkdir(parents=True)

        result = self._run()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("nothing to sync", result.stderr)

    def test_dry_run_reports_mode_without_flag_suffix(self):
        (self.workspace / ".claude/skills").mkdir(parents=True)

        result = self._run("--dry-run")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Mode:      DRY-RUN (no changes written)\n", result.stdout)
        self.assertNotIn("DRY-RUN (no changes written)--dry-run", result.stdout)

    # --- Hook reverse-mapping tests ---

    def test_dot_claude_hooks_map_back_to_repo_hooks_hooks(self):
        """Reverse: .claude/hooks/* (scripts) must land in hooks/hooks/* in the checkout."""
        hooks_dir = self.workspace / ".claude/hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "block-confidential.sh").write_text("#!/bin/sh\necho block\n")
        # Also place a settings.json fragment
        (hooks_dir / "settings.json").write_text('{"hooks":{}}\n')
        # Minimal shared content so SRCS is non-empty
        skills_dir = self.workspace / ".claude/skills"
        skills_dir.mkdir(parents=True)

        result = self._run()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(
            (self.checkout / "hooks/hooks/block-confidential.sh").is_file(),
            "hook script should be at hooks/hooks/ in checkout",
        )

    def test_dot_claude_hooks_settings_json_maps_back_to_hooks_settings_json(self):
        """.claude/hooks/settings.json must map back to hooks/settings.json, not hooks/hooks/settings.json."""
        hooks_dir = self.workspace / ".claude/hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "settings.json").write_text('{"hooks":{}}\n')
        (hooks_dir / "block-confidential.sh").write_text("#!/bin/sh\n")
        # Minimal shared content so SRCS is non-empty
        (self.workspace / ".claude/skills").mkdir(parents=True)

        result = self._run()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(
            (self.checkout / "hooks/settings.json").is_file(),
            "hooks/settings.json must exist in checkout",
        )
        self.assertFalse(
            (self.checkout / "hooks/hooks/settings.json").exists(),
            "settings.json must NOT appear under hooks/hooks/",
        )

    def test_settings_local_json_never_imported(self):
        """workspace .claude/settings.local.json must never be copied to the checkout."""
        (self.workspace / ".claude").mkdir(parents=True)
        (self.workspace / ".claude/settings.local.json").write_text('{"private":true}\n')
        skills = self.workspace / ".claude/skills"
        skills.mkdir()

        (self.checkout / "shared-manifest.txt").write_text("skills\n")

        result = self._run()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(
            (self.checkout / "settings.local.json").exists(),
            "settings.local.json must never cross to checkout",
        )

    def test_hook_symlinks_in_workspace_are_rejected(self):
        """Symlinks under .claude/hooks/ must be rejected by workspace-to-checkout."""
        hooks_dir = self.workspace / ".claude/hooks"
        hooks_dir.mkdir(parents=True)
        outside = self.root / "outside.sh"
        outside.write_text("#!/bin/sh\n")
        (hooks_dir / "linked.sh").symlink_to(outside)

        result = self._run()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source symlink", result.stderr)

    def _run(self, *args):
        return subprocess.run(
            [str(self.sync / "workspace-to-checkout.sh"), str(self.workspace), *args],
            capture_output=True,
            text=True,
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
