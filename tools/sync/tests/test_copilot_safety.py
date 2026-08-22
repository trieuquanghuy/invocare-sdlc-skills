#!/usr/bin/env python3

import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "copilot/generate.py"


class CopilotSafetyTest(unittest.TestCase):
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

    def test_defaults_to_current_workspace_when_run_from_source_repo(self):
        conventional = self.workspace / "conventional"
        (conventional / ".claude/rules").mkdir(parents=True)
        (conventional / ".claude/agents").mkdir()
        (conventional / ".claude/skills/base").mkdir(parents=True)
        (conventional / ".github").mkdir()
        (conventional / ".claude/rules/base.md").write_text("# Base\n")
        (conventional / ".claude/agents/base.md").write_text(
            "---\nname: base\ndescription: Base agent\n---\n# Base\n"
        )
        (conventional / ".claude/skills/base/SKILL.md").write_text(
            "---\nname: base\ndescription: Base prompt\n---\n# Base\n"
        )
        result = subprocess.run(
            ["python3", str(SCRIPT), "--dry-run"],
            cwd=conventional,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("would create 3", result.stdout)

    def test_rejects_source_file_and_parent_symlinks(self):
        outside = self._write("outside.md", "# Outside\n")
        (self.source / "rules/linked.md").symlink_to(outside)
        result = self._run()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source symlink", result.stderr)

    def test_rejects_symlinked_required_source_directory(self):
        rules = self.source / "rules"
        (rules / "base.md").unlink()
        rules.rmdir()
        outside = self.workspace / "outside-rules"
        outside.mkdir()
        rules.symlink_to(outside, target_is_directory=True)

        result = self._run()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source symlink", result.stderr)

    def test_rejects_destination_parent_symlink_before_rendering(self):
        outside = self.workspace / "outside-agents"
        outside.mkdir()
        protected = self._write("outside-agents/base.md", "---\ndescription: Protected\n")
        protected.chmod(0)
        (self.target / "agents").symlink_to(outside)
        try:
            result = self._run()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("symlink destination", result.stderr)
            self.assertNotIn("cannot read", result.stderr)
            self.assertNotIn("unclosed frontmatter", result.stderr)
        finally:
            protected.chmod(0o600)

    def test_rejects_malformed_source_and_destination_frontmatter(self):
        self._write(".claude/agents/base.md", "---\nname: base\n# Missing close\n")
        source_result = self._run()
        self.assertNotEqual(source_result.returncode, 0)
        self.assertIn("unclosed frontmatter", source_result.stderr)

        self._write(
            ".claude/agents/base.md",
            "---\nname: base\ndescription: Base agent\n---\n# Base\n",
        )
        self._write(".github/agents/base.md", "---\ndescription: Broken\n")
        destination_result = self._run()
        self.assertNotEqual(destination_result.returncode, 0)
        self.assertIn("unclosed frontmatter", destination_result.stderr)

    def test_validates_reference_links_and_parenthesized_destinations(self):
        self._write(
            ".claude/skills/base/SKILL.md",
            "---\nname: base\ndescription: Base prompt\n---\n"
            "[Missing][doc]\n[doc]: ./references/missing.md\n",
        )
        broken = self._run("--dry-run")
        self.assertNotEqual(broken.returncode, 0)
        self.assertIn("broken relative link", broken.stderr)

        self._write(
            ".claude/skills/base/SKILL.md",
            "---\nname: base\ndescription: Base prompt\n---\n"
            "[Present](./references/with(paren).md)\n",
        )
        self._write(".claude/skills/base/references/with(paren).md", "# Present\n")
        valid = self._run("--dry-run")
        self.assertEqual(valid.returncode, 0, valid.stderr)

    def test_translates_skill_entry_and_arbitrary_shared_template_paths(self):
        self._write(
            ".claude/skills/base/SKILL.md",
            "---\nname: base\ndescription: Base prompt\n---\n"
            "Read `.claude/skills/other/SKILL.md` and "
            "`.claude/skills/_shared/templates/custom.md`.\n",
        )
        self._write(
            ".claude/skills/other/SKILL.md",
            "---\nname: other\ndescription: Other prompt\n---\n# Other\n",
        )
        self._write(".claude/skills/_shared/templates/custom.md", "# Custom\n")
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        prompt = (self.target / "prompts/base.prompt.md").read_text()
        self.assertIn(".github/prompts/other.prompt.md", prompt)
        self.assertIn(".github/prompts/references/_shared/custom.md", prompt)

    def test_detects_destination_collisions(self):
        self._write(
            ".claude/skills/apply-fix/SKILL.md",
            "---\nname: apply-fix\ndescription: Apply\n---\n# Apply\n",
        )
        self._write(
            ".claude/skills/apply-fix/references/session-log-template.md",
            "# Owned\n",
        )
        self._write(
            ".claude/skills/_shared/templates/session-log-template.md",
            "# Shared\n",
        )
        result = self._run("--dry-run")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("destination collisions", result.stderr)

class ManifestSafetyTest(unittest.TestCase):
    """Regression tests for manifest path safety validation (Task 1)."""

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

    def _apply_and_seed_manifest(self, extra_paths):
        result = self._run()
        assert result.returncode == 0, result.stderr
        manifest = self.target / self.MANIFEST
        existing = {p for p in manifest.read_text().splitlines() if p.strip()}
        existing.update(extra_paths)
        manifest.write_text("\n".join(sorted(existing)) + "\n")

    def test_manifest_rejects_symlink_path_before_prune(self):
        self._apply_and_seed_manifest([])
        # Create a symlink in .github that appears stale
        outside = self.workspace / "outside.md"
        outside.write_text("# Outside\n")
        link = self.target / "prompts" / "symlinked.prompt.md"
        link.symlink_to(outside)
        self._apply_and_seed_manifest(["prompts/symlinked.prompt.md"])
        result = self._run("--prune")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink", result.stderr)
        self.assertTrue(link.exists(), "symlink must not be removed before validation")

    def test_manifest_rejects_absolute_path_before_prune(self):
        self._apply_and_seed_manifest(["/etc/passwd"])
        result = self._run("--prune")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("absolute", result.stderr)

    def test_manifest_rejects_escaping_path_before_prune(self):
        self._apply_and_seed_manifest(["../escape.md"])
        result = self._run("--prune")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("escaping", result.stderr)

    def test_malformed_manifest_paths_block_apply_too(self):
        # Apply mode should also reject malformed paths
        self._apply_and_seed_manifest(["/etc/passwd"])
        result = self._run()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("absolute", result.stderr)

    def test_malformed_manifest_paths_block_check_too(self):
        self._apply_and_seed_manifest(["../escape.md"])
        result = self._run("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("escaping", result.stderr)


if __name__ == "__main__":
    unittest.main()
