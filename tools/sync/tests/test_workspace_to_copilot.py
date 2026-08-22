#!/usr/bin/env python3

import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "copilot/generate.py"


class WorkspaceToCopilotTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.source = self.workspace / "source"
        self.target = self.workspace / "target"
        self._write(".claude/rules/output-guardian.md", "# Output\n")
        self._write(
            ".claude/agents/reviewer.md",
            "---\nname: reviewer\ndescription: Source reviewer\ntools: Read\n---\n"
            "Apply `.claude/rules/output-guardian.md`.\n",
        )
        self._write(
            ".claude/skills/create-spec/SKILL.md",
            "---\nname: create-spec\ndescription: Create a spec\n---\n"
            "[Spec](./references/spec.md)\n"
            "[Validation](../create-validation/references/validation.md)\n"
            "[Ledger](../_shared/templates/deploy-result-template.md)\n"
            "Apply `.claude/rules/output-guardian.md`.\n",
        )
        self._write(
            ".claude/skills/create-spec/checker-prompt.md",
            "Read `.claude/skills/create-spec/references/spec.md`.\n",
        )
        self._write(".claude/skills/create-spec/references/spec.md", "# Spec\n")
        self._write(
            ".claude/skills/create-validation/SKILL.md",
            "---\nname: create-validation\ndescription: Create validation\n---\n"
            "[Template](./references/validation.md)\n",
        )
        self._write(
            ".claude/skills/create-validation/references/validation.md",
            "# Validation\n",
        )
        self._write(
            ".claude/skills/_shared/contracts/checker-contract.md",
            "# Contract\n",
        )
        self._write(
            ".claude/skills/_shared/references/firebase-db-map.md",
            "# DB map\n",
        )
        self._write(
            ".claude/skills/_shared/templates/deploy-result-template.md",
            "# Deploy result\n",
        )
        self._write(
            ".github/agents/reviewer.md",
            "---\ndescription: Copilot reviewer\ntools: ['search']\n---\nOld\n",
        )
        self._write(".github/prompts/copilot-only.prompt.md", "# Keep me\n")

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write(self, relative_path, content):
        if relative_path.startswith(".claude/"):
            path = self.source / relative_path.removeprefix(".claude/")
        elif relative_path.startswith(".github/"):
            path = self.target / relative_path.removeprefix(".github/")
        else:
            path = self.workspace / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def _run(self, *args):
        self.assertTrue(SCRIPT.exists(), "copilot/generate.py must be implemented")
        return subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--source",
                str(self.source),
                "--target",
                str(self.target),
                *args,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_maps_and_translates_source_backed_files(self):
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = [
            ".github/instructions/output-guardian.instructions.md",
            ".github/agents/reviewer.md",
            ".github/prompts/create-spec.prompt.md",
            ".github/prompts/create-spec-checker.prompt.md",
            ".github/prompts/references/create-spec/spec.md",
            ".github/prompts/create-validation.prompt.md",
            ".github/prompts/references/create-validation/validation.md",
            ".github/prompts/references/_shared/checker-contract.md",
            ".github/prompts/_shared/references/firebase-db-map.md",
            ".github/prompts/references/_shared/deploy-result-template.md",
        ]
        for relative_path in expected:
            target_path = relative_path.removeprefix(".github/")
            self.assertTrue((self.target / target_path).is_file(), relative_path)

        prompt = (self.target / "prompts/create-spec.prompt.md").read_text()
        self.assertIn("./references/create-spec/spec.md", prompt)
        self.assertIn("./references/create-validation/validation.md", prompt)
        self.assertIn("./references/_shared/deploy-result-template.md", prompt)
        self.assertIn(".github/instructions/output-guardian.instructions.md", prompt)

    def test_preserves_copilot_frontmatter_and_unmapped_files(self):
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        agent = (self.target / "agents/reviewer.md").read_text()
        self.assertIn("description: Copilot reviewer", agent)
        self.assertIn("tools: ['search']", agent)
        self.assertNotIn("name: reviewer", agent)
        self.assertEqual(
            (self.target / "prompts/copilot-only.prompt.md").read_text(),
            "# Keep me\n",
        )

    def test_dry_run_and_check_report_drift_without_writing(self):
        dry_run = self._run("--dry-run")
        self.assertEqual(dry_run.returncode, 0, dry_run.stderr)
        self.assertIn("would create", dry_run.stdout)
        self.assertFalse(
            (self.target / "prompts/create-spec.prompt.md").exists()
        )
        check = self._run("--check")
        self.assertNotEqual(check.returncode, 0)
        self.assertIn("drift detected", check.stderr)
        self.assertIn(
            ".github/instructions/output-guardian.instructions.md",
            check.stdout,
        )

    def test_apply_is_idempotent_and_check_passes(self):
        first = self._run()
        self.assertEqual(first.returncode, 0, first.stderr)
        check = self._run("--check")
        self.assertEqual(check.returncode, 0, check.stderr)
        second = self._run()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("0 created, 0 updated", second.stdout)

    def test_rejects_symlink_destination(self):
        destination = self.target / "prompts/create-spec.prompt.md"
        destination.parent.mkdir(parents=True, exist_ok=True)
        outside = self.workspace / "outside.md"
        outside.write_text("unchanged\n")
        destination.symlink_to(outside)
        result = self._run()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink", result.stderr)
        self.assertEqual(outside.read_text(), "unchanged\n")


class ManifestOwnershipTest(unittest.TestCase):
    """Regression tests for manifest-backed ownership (Task 1)."""

    MANIFEST = ".invocare-generated-manifest"

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.source = self.workspace / "source"
        self.target = self.workspace / "target"
        self._write(".claude/rules/base.md", "# Base\n")
        self._write(
            ".claude/agents/base.md",
            "---\nname: base\ndescription: Base agent\n---\n# Base\n",
        )
        self._write(
            ".claude/skills/base/SKILL.md",
            "---\nname: base\ndescription: Base prompt\n---\n# Base\n",
        )
        self.target.mkdir()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write(self, relative_path, content):
        if relative_path.startswith(".claude/"):
            path = self.source / relative_path.removeprefix(".claude/")
        elif relative_path.startswith(".github/"):
            path = self.target / relative_path.removeprefix(".github/")
        else:
            path = self.workspace / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def _run(self, *args):
        self.assertTrue(SCRIPT.exists(), "copilot/generate.py must be implemented")
        return subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--source",
                str(self.source),
                "--target",
                str(self.target),
                *args,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def _manifest_path(self):
        return self.target / self.MANIFEST

    def _manifest_paths(self):
        return {p for p in self._manifest_path().read_text().splitlines() if p.strip()}

    def test_manifest_written_after_apply(self):
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self._manifest_path().exists(), "manifest must be written after apply")
        paths = self._manifest_paths()
        self.assertIn("instructions/base.instructions.md", paths)
        self.assertIn("agents/base.md", paths)
        self.assertIn("prompts/base.prompt.md", paths)

    def test_manifest_paths_are_sorted(self):
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = [l for l in self._manifest_path().read_text().splitlines() if l.strip()]
        self.assertEqual(lines, sorted(lines), "manifest paths must be sorted")

    def test_missing_manifest_adopts_current_mappings_without_stale(self):
        self.assertFalse(self._manifest_path().exists())
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("stale", result.stdout)
        self.assertNotIn("stale", result.stderr)

    def test_check_fails_and_reports_stale_from_manifest(self):
        # Seed manifest with an extra (stale) path not in current mappings
        self._manifest_path().write_text(
            "agents/base.md\n"
            "instructions/base.instructions.md\n"
            "prompts/base.prompt.md\n"
            "prompts/old-removed.prompt.md\n"
        )
        result = self._run("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stale", result.stderr)

    def test_apply_reports_stale_but_preserves_file(self):
        # Apply first to create generated files and manifest
        first = self._run()
        self.assertEqual(first.returncode, 0, first.stderr)
        # Create a stale file and add it to the manifest
        stale = self.target / "prompts" / "old-removed.prompt.md"
        stale.write_text("# Old\n")
        manifest_paths = self._manifest_paths()
        manifest_paths.add("prompts/old-removed.prompt.md")
        self._manifest_path().write_text("\n".join(sorted(manifest_paths)) + "\n")
        # Apply without --prune
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("stale", result.stdout)
        self.assertTrue(stale.exists(), "stale file must be preserved without --prune")

    def test_prune_removes_stale_files_and_empty_dirs(self):
        first = self._run()
        self.assertEqual(first.returncode, 0, first.stderr)
        # Add stale file in a fresh subdirectory
        stale_dir = self.target / "prompts" / "stale-skill"
        stale_dir.mkdir(parents=True, exist_ok=True)
        stale_file = stale_dir / "old.prompt.md"
        stale_file.write_text("# Old\n")
        manifest_paths = self._manifest_paths()
        manifest_paths.add("prompts/stale-skill/old.prompt.md")
        self._manifest_path().write_text("\n".join(sorted(manifest_paths)) + "\n")
        # Run with --prune
        result = self._run("--prune")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(stale_file.exists(), "stale file must be removed by --prune")
        self.assertFalse(stale_dir.exists(), "empty parent dir must be removed by --prune")
        self.assertIn("removed", result.stdout)

    def test_prune_preserves_non_empty_dirs(self):
        first = self._run()
        self.assertEqual(first.returncode, 0, first.stderr)
        # Add stale file alongside a non-stale file in same dir
        stale_file = self.target / "prompts" / "references" / "stale-skill" / "old.md"
        stale_file.parent.mkdir(parents=True, exist_ok=True)
        stale_file.write_text("# Old\n")
        keeper = self.target / "prompts" / "references" / "stale-skill" / "keep.md"
        keeper.write_text("# Keep\n")
        manifest_paths = self._manifest_paths()
        manifest_paths.add("prompts/references/stale-skill/old.md")
        self._manifest_path().write_text("\n".join(sorted(manifest_paths)) + "\n")
        result = self._run("--prune")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(stale_file.exists(), "stale file must be removed")
        self.assertTrue(keeper.exists(), "non-stale file in same dir must be preserved")
        self.assertTrue(stale_file.parent.exists(), "non-empty parent dir must not be removed")

    def test_dry_run_prune_previews_removals_without_writing(self):
        first = self._run()
        self.assertEqual(first.returncode, 0, first.stderr)
        # Add stale file
        stale = self.target / "prompts" / "preview-me.prompt.md"
        stale.write_text("# Old\n")
        manifest_paths = self._manifest_paths()
        manifest_paths.add("prompts/preview-me.prompt.md")
        original_manifest = "\n".join(sorted(manifest_paths)) + "\n"
        self._manifest_path().write_text(original_manifest)
        # Dry-run prune
        result = self._run("--dry-run", "--prune")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("would remove", result.stdout)
        self.assertTrue(stale.exists(), "stale file must not be removed in dry-run")
        self.assertEqual(
            self._manifest_path().read_text(),
            original_manifest,
            "manifest must not be updated in dry-run",
        )

    def test_check_prune_is_rejected(self):
        result = self._run("--check", "--prune")
        self.assertNotEqual(result.returncode, 0)

    def test_manifest_not_written_in_check_or_dry_run(self):
        # --check with no prior manifest → drift exists (not yet applied), no manifest written
        result = self._run("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self._manifest_path().exists(), "check must not write manifest")
        # --dry-run with no prior manifest → no manifest written
        result = self._run("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self._manifest_path().exists(), "dry-run must not write manifest")

    def test_manifest_updated_after_apply_idempotent(self):
        first = self._run()
        self.assertEqual(first.returncode, 0, first.stderr)
        first_manifest = self._manifest_path().read_text()
        second = self._run()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(
            self._manifest_path().read_text(),
            first_manifest,
            "manifest content must be stable across idempotent applies",
        )

    def test_copilot_only_files_not_in_manifest(self):
        # Write a copilot-only file that is NOT generated
        copilot_only = self.target / "prompts" / "copilot-only.prompt.md"
        copilot_only.parent.mkdir(parents=True, exist_ok=True)
        copilot_only.write_text("# Keep me\n")
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest_paths = self._manifest_paths()
        self.assertNotIn("prompts/copilot-only.prompt.md", manifest_paths)
        self.assertTrue(copilot_only.exists(), "copilot-only file must be preserved")

    def test_prune_never_removes_copilot_only_files(self):
        first = self._run()
        self.assertEqual(first.returncode, 0, first.stderr)
        # Copilot-only file not in manifest
        copilot_only = self.target / "prompts" / "copilot-only.prompt.md"
        copilot_only.write_text("# Keep me\n")
        result = self._run("--prune")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(copilot_only.exists(), "prune must never remove copilot-only files")


if __name__ == "__main__":
    unittest.main()
