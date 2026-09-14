#!/usr/bin/env python3

import subprocess
import tempfile
import unittest
from pathlib import Path


SYNC_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SYNC_DIR / "copilot/generate.py"
ROOT = SYNC_DIR.parents[1]


class NativeCopilotSkillsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / ".claude"
        self.target = self.root / ".github"
        (self.source / "rules").mkdir(parents=True)
        (self.source / "agents").mkdir()
        self.skill_text = (
            "---\nname: demo\ndescription: Use when demonstrating a workflow.\n"
            "argument-hint: ticket\n"
            "disable-model-invocation: true\n---\n# Demo\n"
        )
        self._write("skills/demo/SKILL.md", self.skill_text)

    def tearDown(self):
        self.temporary.cleanup()

    def _write(self, relative, content):
        path = self.source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content)
        return path

    def _run(self, *args, source=None):
        return subprocess.run(
            [
                "python3", str(SCRIPT),
                "--source", str(source or self.source),
                "--target", str(self.target),
                *args,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_generates_native_skill_with_invocation_metadata(self):
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        destination = self.target / "skills/demo/SKILL.md"
        self.assertTrue(destination.is_file(), result.stdout)
        self.assertEqual(destination.read_text(), self.skill_text)
        self.assertFalse((self.target / "prompts").exists())

    def test_copies_complete_bundle_and_executable_resources(self):
        self._write(
            "skills/demo/SKILL.md",
            self.skill_text + "[Guide](references/guide.md)\n"
            "[Script](scripts/run.sh)\n[Image](assets/logo.png)\n"
            "[Checker](./checker-prompt.md)\n",
        )
        self._write("skills/demo/references/guide.md", "# Guide\n")
        self._write("skills/demo/checker-prompt.md", "# Checker\n")
        script = self._write(
            "skills/demo/scripts/run.sh",
            '#!/bin/sh\nprintf ".claude/skills/demo is literal data\\n"\n',
        )
        script.chmod(0o755)
        image = self._write("skills/demo/assets/logo.png", b"\x89PNG\r\n\xff\x00")
        self._write("skills/demo/LICENSE.txt", "License text\n")

        result = self._run()

        self.assertEqual(result.returncode, 0, result.stderr)
        bundle = self.target / "skills/demo"
        self.assertTrue((bundle / "scripts/run.sh").exists(), result.stdout)
        self.assertEqual((bundle / "scripts/run.sh").read_bytes(), script.read_bytes())
        self.assertEqual((bundle / "scripts/run.sh").stat().st_mode & 0o777, 0o755)
        self.assertEqual((bundle / "assets/logo.png").read_bytes(), image.read_bytes())
        self.assertEqual((bundle / "LICENSE.txt").read_text(), "License text\n")
        self.assertTrue((bundle / "checker-prompt.md").is_file())
        again = self._run("--check")
        self.assertEqual(again.returncode, 0, again.stderr)

    def test_preserves_relative_paths_and_shared_resource_layout(self):
        self._write(
            "skills/demo/SKILL.md",
            self.skill_text
            + "[Shared](../_shared/templates/common.md)\n"
            "[Other](../other/SKILL.md)\n"
            "Read `.claude/skills/other/SKILL.md`, "
            "`.claude/skills/demo/scripts/run.sh`, "
            "`.claude/skills/_shared/contracts/common.md`, "
            "`.claude/rules/base.md`, and `.claude/agents/base.md`.\n"
            "Find `.claude/skills/*/checker-prompt.md` and `.claude/skills/**`.\n",
        )
        self._write("rules/base.md", "# Base\n")
        self._write("agents/base.md", "---\ndescription: Base\n---\n# Base\n")
        self._write(
            "skills/other/SKILL.md",
            "---\nname: other\ndescription: Another skill.\n---\n# Other\n",
        )
        self._write("skills/_shared/templates/common.md", "# Template\n")
        self._write("skills/_shared/contracts/common.md", "# Contract\n")
        self._write("skills/demo/scripts/run.sh", "#!/bin/sh\nexit 0\n")

        result = self._run()

        self.assertEqual(result.returncode, 0, result.stderr)
        destination = self.target / "skills/demo/SKILL.md"
        self.assertTrue(destination.is_file(), result.stdout)
        content = destination.read_text()
        self.assertIn("../_shared/templates/common.md", content)
        self.assertIn("../other/SKILL.md", content)
        self.assertIn(".github/skills/other/SKILL.md", content)
        self.assertIn(".github/skills/demo/scripts/run.sh", content)
        self.assertIn(".github/skills/_shared/contracts/common.md", content)
        self.assertIn(".github/instructions/base.instructions.md", content)
        self.assertIn(".github/agents/base.md", content)
        self.assertIn(".github/skills/*/checker-prompt.md", content)
        self.assertIn(".github/skills/**", content)
        self.assertEqual(
            (self.target / "skills/_shared/contracts/common.md").read_text(),
            "# Contract\n",
        )

    def test_rejects_invalid_skill_metadata_before_writing(self):
        invalid = (
            "# No frontmatter\n",
            "---\ndescription: Missing name\n---\n",
            "---\nname: demo\n---\n",
            "---\nname: different\ndescription: Mismatched\n---\n",
            "---\nname: demo\ndescription: ''\n---\n",
            "---\nname: demo\ndescription: true\n---\n",
            "---\nname: demo\ndescription: broken: yaml\n---\n",
            "---\nname: demo\nname: demo\ndescription: Duplicate\n---\n",
            "---\nname: demo\ndescription: " + "x" * 1025 + "\n---\n",
            "---\nname: demo\ndescription: Demo\n"
            "disable-model-invocation: 'true'\n---\n",
        )
        for text in invalid:
            with self.subTest(frontmatter=text[:100]):
                self._write("skills/demo/SKILL.md", text)
                result = self._run()
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("SKILL.md", result.stderr)
                self.assertFalse(self.target.exists(), result.stdout)

    def test_rejects_invalid_skill_names(self):
        (self.source / "skills/demo/SKILL.md").unlink()
        (self.source / "skills/demo").rmdir()
        for name in ("Upper", "has_underscore", "-leading", "trailing-", "two--hyphens", "x" * 65):
            with self.subTest(name=name):
                skill = self._write(
                    f"skills/{name}/SKILL.md",
                    f"---\nname: {name}\ndescription: A skill\n---\n",
                )
                result = self._run("--dry-run")
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("name", result.stderr)
                skill.unlink()
                skill.parent.rmdir()

    def test_accepts_folded_description_and_preserves_optional_metadata(self):
        text = (
            "---\nname: demo\ndescription: >-\n"
            "  Use when a description\n  spans multiple lines.\n"
            "license: MIT\nmetadata:\n  owner: team\n"
            "allowed-tools: read\n"
            "disable-model-invocation: true\n---\n# Demo\n"
        )
        self._write("skills/demo/SKILL.md", text)
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        destination = self.target / "skills/demo/SKILL.md"
        self.assertTrue(destination.exists(), result.stdout)
        self.assertEqual(destination.read_text(), text)

    def test_validates_standard_relative_resource_links(self):
        self._write(
            "skills/demo/SKILL.md",
            self.skill_text + "[Missing](references/missing.md)\n",
        )
        result = self._run("--dry-run")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("broken relative link", result.stderr)

    def test_rejects_symlinked_resource_directory(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "run.sh").write_text("#!/bin/sh\nexit 0\n")
        (self.source / "skills/demo/scripts").symlink_to(outside, target_is_directory=True)
        result = self._run()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("source symlink", result.stderr)
        self.assertFalse(self.target.exists())

    def test_ignores_hidden_and_local_skills(self):
        self._write("skills/.hidden/SKILL.md", "# Not a shared skill\n")
        self._write("skills/_local/personal/SKILL.md", "# Personal\n")
        self._write("skills/demo/.cache/data.bin", b"\xff\xfe")
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(".hidden", result.stdout)
        self.assertNotIn("_local", result.stdout)
        self.assertFalse((self.target / "skills/demo/.cache").exists())

    def test_refuses_to_overwrite_unmanaged_native_skill(self):
        destination = self.target / "skills/demo/SKILL.md"
        destination.parent.mkdir(parents=True)
        custom = "---\nname: demo\ndescription: Custom CLI wrapper\n---\n# Keep\n"
        destination.write_text(custom)
        for mode in (("--dry-run",), ("--check",), (), ("--prune",)):
            with self.subTest(mode=mode):
                result = self._run(*mode)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("unmanaged", result.stderr)
                self.assertIn(str(destination), result.stderr)
                self.assertEqual(destination.read_text(), custom)
                self.assertFalse((self.target / ".invocare-generated-manifest").exists())

    def test_adopts_identical_native_files_then_updates_owned_files(self):
        destination = self.target / "skills/demo/SKILL.md"
        destination.parent.mkdir(parents=True)
        destination.write_text(self.skill_text)
        first = self._run()
        self.assertEqual(first.returncode, 0, first.stderr)
        manifest = self.target / ".invocare-generated-manifest"
        self.assertIn("skills/demo/SKILL.md", manifest.read_text())
        self._write("skills/demo/SKILL.md", self.skill_text + "\nNew instructions.\n")
        second = self._run()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("New instructions.", destination.read_text())

    def test_legacy_prompts_stay_owned_until_explicit_prune(self):
        legacy = self.target / "prompts/demo.prompt.md"
        legacy.parent.mkdir(parents=True)
        legacy.write_text(self.skill_text)
        manifest = self.target / ".invocare-generated-manifest"
        manifest.write_text("prompts/demo.prompt.md\n")

        applied = self._run()

        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertIn("stale", applied.stdout)
        self.assertTrue(legacy.exists())
        self.assertIn("prompts/demo.prompt.md", manifest.read_text())
        self.assertIn("skills/demo/SKILL.md", manifest.read_text())
        drift = self._run("--check")
        self.assertNotEqual(drift.returncode, 0)
        self.assertIn("stale", drift.stderr)
        pruned = self._run("--prune")
        self.assertEqual(pruned.returncode, 0, pruned.stderr)
        self.assertFalse(legacy.exists())
        self.assertNotIn("prompts/demo.prompt.md", manifest.read_text())
        self.assertEqual(self._run("--check").returncode, 0)

    def test_generates_repository_skills_and_their_scripts(self):
        result = self._run(source=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        sources = sorted(
            path for path in (ROOT / "skills").glob("*/SKILL.md")
            if not path.parent.name.startswith(("_", "."))
        )
        for source in sources:
            self.assertTrue(
                (self.target / "skills" / source.parent.name / "SKILL.md").is_file(),
                str(source),
            )
        self.assertTrue((self.target / "skills/create-pr/scripts/git-facts.sh").is_file())
        self.assertTrue((self.target / "skills/task-status/scripts/extract.sh").is_file())
        self.assertFalse((self.target / "prompts").exists())

    def test_runtime_config_is_never_copied_or_owned(self):
        self._write(
            "skills/demo/SKILL.md",
            self.skill_text + "Use `.claude/skills/_shared/config/drive.json`.\n",
        )
        self._write("skills/_shared/config/drive.json", '{"folder": "source"}\n')
        destination = self.target / "skills/_shared/config/drive.json"
        destination.parent.mkdir(parents=True)
        destination.write_text('{"folder": "local"}\n')

        result = self._run("--prune")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(destination.read_text(), '{"folder": "local"}\n')
        manifest = (self.target / ".invocare-generated-manifest").read_text()
        self.assertNotIn("skills/_shared/config/", manifest)
        content = (self.target / "skills/demo/SKILL.md").read_text()
        self.assertIn(".claude/skills/_shared/config/drive.json", content)

    def test_absent_runtime_config_keeps_its_workspace_path(self):
        self._write(
            "skills/demo/SKILL.md",
            self.skill_text
            + "Create `.claude/skills/_shared/config/drive.json` on first use.\n"
            "The directory is `.claude/skills/_shared/config`.\n"
            "Examples: `.claude/skills/_shared/config-examples/drive.json`.\n",
        )
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        content = (self.target / "skills/demo/SKILL.md").read_text()
        self.assertIn(".claude/skills/_shared/config/drive.json", content)
        self.assertIn("`.claude/skills/_shared/config`", content)
        self.assertIn(".github/skills/_shared/config-examples/drive.json", content)
        self.assertFalse((self.target / "skills/_shared/config").exists())

    def test_rejects_incorrectly_cased_skill_entry(self):
        entry = self.source / "skills/demo/SKILL.md"
        temporary = entry.with_name("entry.tmp")
        lower = entry.with_name("skill.md")
        entry.rename(temporary)
        temporary.rename(lower)
        for text in ("# Missing metadata\n", self.skill_text):
            with self.subTest(text=text):
                lower.write_text(text)
                result = self._run("--dry-run")
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("SKILL.md", result.stderr)

    def _require_case_insensitive_filesystem(self):
        probe = self.root / "case-probe"
        probe.write_text("probe\n")
        if not (self.root / "CASE-PROBE").exists():
            self.skipTest("requires a case-insensitive filesystem")

    def _prepare_case_only_resource_rename(self):
        self._require_case_insensitive_filesystem()
        source = self._write("skills/demo/scripts/Run.sh", "#!/bin/sh\nexit 0\n")
        first = self._run()
        self.assertEqual(first.returncode, 0, first.stderr)
        temporary = source.with_name("renaming.tmp")
        source.rename(temporary)
        temporary.rename(source.with_name("run.sh"))
        return self.target / "skills/demo/scripts/Run.sh"

    def test_rejects_incorrect_native_destination_casing(self):
        self._require_case_insensitive_filesystem()
        destination = self.target / "skills/demo/skill.md"
        destination.parent.mkdir(parents=True)
        destination.write_text(self.skill_text)
        result = self._run()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("case-only rename", result.stderr)
        self.assertEqual(destination.read_text(), self.skill_text)

    def test_rejects_incorrect_parent_casing_before_creating_skill(self):
        self._require_case_insensitive_filesystem()
        directory = self.target / "skills/Demo"
        directory.mkdir(parents=True)
        result = self._run()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("case-only rename", result.stderr)
        self.assertFalse((directory / "SKILL.md").exists())

    def test_case_only_resource_rename_cannot_delete_active_file(self):
        original = self._prepare_case_only_resource_rename()
        manifest = self.target / ".invocare-generated-manifest"
        before = manifest.read_bytes()
        for mode in ((), ("--dry-run",), ("--prune",)):
            with self.subTest(mode=mode):
                result = self._run(*mode)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("case-only rename", result.stderr)
                self.assertTrue(original.is_file())
                self.assertEqual(manifest.read_bytes(), before)

    def test_reconciles_case_alias_ownership_after_destination_rename(self):
        original = self._prepare_case_only_resource_rename()
        temporary = original.with_name("renaming.tmp")
        original.rename(temporary)
        temporary.rename(original.with_name("run.sh"))

        result = self._run("--prune")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(original.with_name("run.sh").is_file())
        manifest = (self.target / ".invocare-generated-manifest").read_text()
        self.assertNotIn("scripts/Run.sh", manifest)
        self.assertIn("scripts/run.sh", manifest)
        check = self._run("--check")
        self.assertEqual(check.returncode, 0, check.stderr)


if __name__ == "__main__":
    unittest.main()
