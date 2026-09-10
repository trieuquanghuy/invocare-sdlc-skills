#!/usr/bin/env python3
"""Policy tests for local repository governance artifacts."""

import os
from pathlib import Path
import subprocess
import unittest


TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent.parents[1]

REQUIRED_FILES = (
    ".github/CODEOWNERS",
    "LICENSE",
    "scripts/validate-calver.sh",
)


class TestRepositoryPolicy(unittest.TestCase):
    def test_required_files_exist(self):
        missing = [path for path in REQUIRED_FILES if not (ROOT / path).is_file()]
        self.assertEqual(missing, [], f"missing required files: {missing}")

    def test_ci_cd_workflows_are_not_configured(self):
        workflows = ROOT / ".github" / "workflows"
        configured = (
            sorted(path.name for path in workflows.iterdir() if path.is_file())
            if workflows.is_dir()
            else []
        )
        self.assertEqual(
            configured,
            [],
            f"CI/CD workflows are not supported in this repository: {configured}",
        )


class TestCodeowners(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")

    def test_catch_all_owner_exists(self):
        rules = [
            line.strip()
            for line in self.text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertIn("* @trieuquanghuy", rules)


class TestLicense(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / "LICENSE").read_text(encoding="utf-8")

    def test_full_mit_license_is_present(self):
        self.assertIn("MIT License", self.text)
        self.assertIn("Copyright (c) 2026 Huy Trieu", self.text)
        self.assertIn("Permission is hereby granted", self.text)
        self.assertIn("THE SOFTWARE IS PROVIDED", self.text)


class TestValidateCalver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = ROOT / "scripts" / "validate-calver.sh"

    def _run(self, *args):
        return subprocess.run(
            ["bash", str(self.script), *args],
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )

    def test_safe_shell_flags(self):
        text = self.script.read_text(encoding="utf-8")
        self.assertIn("set -euo pipefail", text)

    def test_valid_dates(self):
        for tag in ("v2026.08.22", "v2024.02.29"):
            with self.subTest(tag=tag):
                result = self._run(tag)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_dates_and_formats(self):
        for tag in ("v2023.02.29", "v2026.13.01", "2026.08.22", "vXXXX.08.22"):
            with self.subTest(tag=tag):
                result = self._run(tag)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(result.stderr.strip())

    def test_missing_argument(self):
        result = self._run()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(result.stderr.strip())


if __name__ == "__main__":
    unittest.main()
