#!/usr/bin/env python3

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


SCRIPT = Path(__file__).resolve().parents[1] / "copilot/generate.py"
MANIFEST = ".invocare-generated-manifest"


class CopilotNativeModeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.source = self.workspace / ".claude"
        self.target = self.workspace / ".github"
        self._write(
            ".claude/rules/base.md",
            "# Base\nRead `.claude/skills/base/SKILL.md`.\n",
        )
        self._write(
            ".claude/agents/base.md",
            "---\nname: base\ndescription: Base agent\ntools: [Read]\n---\n"
            "Read `.claude/skills/base/SKILL.md` and `.claude/rules/base.md`.\n",
        )
        self.skill_text = (
            "---\nname: base\ndescription: Base skill\n"
            'argument-hint: "[file]"\ndisable-model-invocation: true\n---\n'
            "[Reference](./references/base.md)\nRead `.claude/rules/base.md`.\n"
        )
        self._write(".claude/skills/base/SKILL.md", self.skill_text)
        self._write(".claude/skills/base/references/base.md", "# Reference\n")
        binary = self._write(".claude/skills/base/assets/sample.bin", "")
        binary.write_bytes(b"\x00\xff\x80\n")

    def _write(self, relative, content):
        path = self.workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def _run(self, *args, workspace=True):
        command = [sys.executable, str(SCRIPT)]
        if workspace:
            command.append(str(self.workspace))
        return subprocess.run(
            [*command, *args], capture_output=True, text=True, check=False
        )

    def _snapshot(self, root):
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        }

    def test_native_reuses_source_without_copying_or_rewriting_it(self):
        original = self._snapshot(self.source)
        result = self._run("--skills-mode", "native")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.target / "skills").exists())
        self.assertEqual(self._snapshot(self.source), original)
        rule = (self.target / "instructions/base.instructions.md").read_text()
        agent = (self.target / "agents/base.md").read_text()
        self.assertIn(".claude/skills/base/SKILL.md", rule)
        self.assertIn(".claude/skills/base/SKILL.md", agent)
        self.assertIn(".github/instructions/base.instructions.md", agent)
        self.assertEqual(
            set((self.target / MANIFEST).read_text().splitlines()),
            {"instructions/base.instructions.md", "agents/base.md"},
        )
        check = self._run("--skills-mode", "native", "--check")
        self.assertEqual(check.returncode, 0, check.stderr)

    def test_mirroring_remains_the_default(self):
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        skill = (self.target / "skills/base/SKILL.md").read_text()
        self.assertIn(".github/instructions/base.instructions.md", skill)
        self.assertIn("disable-model-invocation: true", skill)
        self.assertEqual(
            (self.target / "skills/base/assets/sample.bin").read_bytes(),
            b"\x00\xff\x80\n",
        )

    def test_native_requires_adjacent_conventional_directories(self):
        alternate = self.workspace / "alternate"
        result = self._run(
            "--source", str(self.source), "--target", str(alternate),
            "--skills-mode", "native", workspace=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("adjacent", result.stderr)
        self.assertFalse(alternate.exists())

    def test_native_still_validates_skill_metadata(self):
        self._write(
            ".claude/skills/base/SKILL.md",
            "---\nname: wrong\ndescription: Base\n---\n# Base\n",
        )
        result = self._run("--skills-mode", "native")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid skill name", result.stderr)
        self.assertFalse(self.target.exists())

    def test_native_still_validates_resource_links(self):
        self._write(
            ".claude/skills/base/SKILL.md",
            self.skill_text + "[Missing](./references/missing.md)\n",
        )
        result = self._run("--skills-mode", "native")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("broken relative link", result.stderr)
        self.assertFalse(self.target.exists())

    def test_native_rejects_symlinked_resources(self):
        outside = self._write("outside.md", "# Outside\n")
        (self.source / "skills/base/references/link.md").symlink_to(outside)
        result = self._run("--skills-mode", "native")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source symlink", result.stderr)
        self.assertFalse(self.target.exists())

    def test_owned_mirrors_need_explicit_pruning_before_native_reuse(self):
        mirror = self._run()
        self.assertEqual(mirror.returncode, 0, mirror.stderr)
        before = self._snapshot(self.target)

        blocked = self._run("--skills-mode", "native")
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("shadow", blocked.stderr)
        self.assertIn("--prune", blocked.stderr)
        self.assertEqual(self._snapshot(self.target), before)

        preview = self._run("--skills-mode", "native", "--prune", "--dry-run")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertIn("would remove: .github/skills/base/SKILL.md", preview.stdout)
        self.assertEqual(self._snapshot(self.target), before)

        applied = self._run("--skills-mode", "native", "--prune")
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertFalse((self.target / "skills").exists())
        self.assertEqual(
            (self.source / "skills/base/SKILL.md").read_text(), self.skill_text
        )
        check = self._run("--skills-mode", "native", "--check")
        self.assertEqual(check.returncode, 0, check.stderr)

    def test_pruning_never_removes_an_unowned_github_shadow(self):
        self._write(".github/skills/base/SKILL.md", self.skill_text)
        before = self._snapshot(self.target)
        result = self._run("--skills-mode", "native", "--prune")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unmanaged", result.stderr)
        self.assertIn("shadow", result.stderr)
        self.assertEqual(self._snapshot(self.target), before)
        self.assertFalse((self.target / MANIFEST).exists())

    def test_agents_skill_directory_also_shadows_native_skills(self):
        self._write(".agents/skills/base/SKILL.md", self.skill_text)
        result = self._run("--skills-mode", "native", "--prune")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(".agents", result.stderr)
        self.assertIn("shadow", result.stderr)
        self.assertFalse(self.target.exists())

    def test_shadow_matching_uses_declared_skill_name(self):
        self._write(".github/skills/different-directory/SKILL.md", self.skill_text)
        result = self._run("--skills-mode", "native")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("shadow", result.stderr)
        self.assertIn("different-directory", result.stderr)

    def test_native_preserves_unrelated_higher_priority_skills(self):
        custom = self._write(
            ".github/skills/custom/SKILL.md",
            "---\nname: custom\ndescription: Local skill\n---\n# Custom\n",
        )
        result = self._run("--skills-mode", "native", "--prune")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(custom.is_file())
        self.assertNotIn("skills/custom", (self.target / MANIFEST).read_text())
        self.assertFalse((self.target / "skills/base").exists())

    def test_native_rejects_symlinked_higher_priority_skill_roots(self):
        outside = self.workspace / "external-skills"
        outside.mkdir()
        self.target.mkdir()
        (self.target / "skills").symlink_to(outside, target_is_directory=True)
        result = self._run("--skills-mode", "native")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink", result.stderr)
        self.assertFalse((self.target / MANIFEST).exists())
        self.assertEqual(list(outside.iterdir()), [])

    def test_switching_back_to_mirror_is_supported(self):
        native = self._run("--skills-mode", "native")
        self.assertEqual(native.returncode, 0, native.stderr)
        mirrored = self._run()
        self.assertEqual(mirrored.returncode, 0, mirrored.stderr)
        self.assertTrue((self.target / "skills/base/SKILL.md").is_file())
        self.assertIn(
            ".github/skills/base/SKILL.md",
            (self.target / "agents/base.md").read_text(),
        )
        check = self._run("--check")
        self.assertEqual(check.returncode, 0, check.stderr)

    def test_nested_rule_scope_and_references_survive_generation(self):
        self._write(
            ".claude/rules/frontend/forms.md",
            "---\npaths:\n  - src/forms/**\n"
            "  - tests/forms/**/*.{ts,tsx}\n---\n# Forms\n",
        )
        agent = self.source / "agents/base.md"
        agent.write_text(
            agent.read_text() + "Read `.claude/rules/frontend/forms.md`.\n"
        )
        result = self._run("--skills-mode", "native")

        self.assertEqual(result.returncode, 0, result.stderr)
        output = self.target / "instructions/frontend/forms.instructions.md"
        self.assertTrue(output.is_file())
        metadata = yaml.safe_load(output.read_text().split("---\n")[1])
        self.assertEqual(
            {part.strip() for part in metadata["applyTo"].split(",")},
            {"src/forms/**", "tests/forms/**/*.ts", "tests/forms/**/*.tsx"},
        )
        self.assertIn(
            ".github/instructions/frontend/forms.instructions.md",
            (self.target / "agents/base.md").read_text(),
        )

    def test_nested_rule_symlinks_are_rejected_before_writes(self):
        outside = self._write("external-rules/nested.md", "# Outside\n").parent
        (self.source / "rules/frontend").symlink_to(outside, target_is_directory=True)
        result = self._run("--skills-mode", "native")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source symlink", result.stderr)
        self.assertFalse(self.target.exists())

    def test_nested_rule_references_support_spaces_in_source_paths(self):
        self._write(".claude/rules/nested rules/style guide.md", "# Style\n")
        agent = self.source / "agents/base.md"
        agent.write_text(
            agent.read_text() + "Read `.claude/rules/nested rules/style guide.md`.\n"
        )
        result = self._run()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(
            (self.target / "instructions/nested rules/style guide.instructions.md").is_file()
        )
        self.assertIn(
            ".github/instructions/nested rules/style guide.instructions.md",
            (self.target / "agents/base.md").read_text(),
        )

    def test_native_skill_only_source_can_create_an_empty_ownership_manifest(self):
        (self.source / "agents/base.md").unlink()
        (self.source / "rules/base.md").unlink()
        self._write(
            ".claude/skills/base/SKILL.md",
            "---\nname: base\ndescription: Base\n---\n"
            "[Reference](./references/base.md)\n",
        )
        result = self._run("--skills-mode", "native")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.target / MANIFEST).read_text(), "")
        self.assertFalse((self.target / "skills").exists())
        check = self._run("--skills-mode", "native", "--check")
        self.assertEqual(check.returncode, 0, check.stderr)


if __name__ == "__main__":
    unittest.main()
