#!/usr/bin/env python3

from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "copilot/generate.py"


class CopilotSourceTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / ".claude"
        self.target = self.root / ".github"
        (self.source / "rules").mkdir(parents=True)
        (self.source / "agents").mkdir()
        (self.source / "skills/demo/references").mkdir(parents=True)
        (self.source / "rules/base.md").write_text("# Base\n")
        (self.source / "agents/base.md").write_text(
            "---\ndescription: Base\n---\n# Base\n"
        )
        (self.source / "skills/demo/SKILL.md").write_text("# Demo\n")
        self.target.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def test_ignores_hidden_reference_files(self):
        (self.source / "skills/demo/references/.DS_Store").write_bytes(b"\xff\xfe")

        result = self._run("--dry-run")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(".DS_Store", result.stdout)

    def test_reports_non_text_source_path(self):
        binary = self.source / "skills/demo/references/sample.bin"
        binary.write_bytes(b"\xff\xfe")

        result = self._run("--dry-run")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"non-text source: {binary}", result.stderr)

    def test_generated_files_keep_existing_permissions(self):
        destination = self.target / "prompts/demo.prompt.md"
        destination.parent.mkdir(parents=True)
        destination.write_text("old\n")
        destination.chmod(0o644)

        result = self._run()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(destination.stat().st_mode & 0o777, 0o644)

    def test_reports_paths_and_replaces_existing_files_atomically(self):
        destination = self.target / "instructions/base.instructions.md"
        destination.parent.mkdir(parents=True)
        destination.write_text(
            '---\napplyTo: "**"\ndescription: "Base"\n---\nOld\n'
        )
        old_inode = destination.stat().st_ino

        preview = self._run("--dry-run")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertIn(
            "would update: .github/instructions/base.instructions.md",
            preview.stdout,
        )
        result = self._run()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(destination.stat().st_ino, old_inode)
        self.assertIn("# Base", destination.read_text())

    def test_reports_resolved_source_and_target_roots(self):
        result = self._run("--dry-run")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"Source: {self.source}", result.stdout)
        self.assertIn(f"Target: {self.target}", result.stdout)

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


if __name__ == "__main__":
    unittest.main()
