#!/usr/bin/env python3

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/code-review-kms/references/split_review_artifacts.py"


class SplitReviewArtifactsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.diff = self.root / "local-diff.patch"
        self.plan = self.root / "plan.json"
        self.output = self.root / "review-artifacts"

    def tearDown(self):
        self.temporary.cleanup()

    def _run(self, *args):
        return subprocess.run(
            [
                sys.executable, str(SCRIPT),
                "--diff", str(self.diff),
                "--out-dir", str(self.output),
                *args,
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )

    def _section(self, path, *, quoted=False):
        source, destination = f"a/{path}", f"b/{path}"
        if quoted:
            source, destination = f'"{source}"', f'"{destination}"'
        return (
            f"diff --git {source} {destination}\n"
            f"--- {source}\n+++ {destination}\n"
            "@@ -1 +1 @@\n-before\n+after\n"
        )

    def test_splits_git_quoted_paths_using_decoded_plan_membership(self):
        paths = (
            (r"src/caf\303\251.ts", "src/caf\u00e9.ts"),
            (r"src/\360\237\230\200.ts", "src/\U0001f600.ts"),
            (r'src/quote\"and\\backslash.ts', 'src/quote"and\\backslash.ts'),
            (r"src/line\nand\ttab.ts", "src/line\nand\ttab.ts"),
            (r"src/control\a\b\f\r\v.ts", "src/control\a\b\f\r\v.ts"),
            (r"src/literal\\303\\251.ts", "src/literal\\303\\251.ts"),
            ("src/caf\u00e9\\t.ts", "src/caf\u00e9\t.ts"),
            (r'src/quote\" b/nested.ts', 'src/quote" b/nested.ts'),
        )
        sections = [self._section(encoded, quoted=True) for encoded, _ in paths]
        artifacts = {
            f"artifact-{index}": [decoded]
            for index, (_, decoded) in enumerate(paths, 1)
        }
        self.diff.write_text("".join(sections), encoding="utf-8")
        self.plan.write_text(json.dumps({
            "artifacts": artifacts,
            "lenses": {"reviewer": list(artifacts)},
        }))

        result = self._run("--plan", str(self.plan))

        self.assertEqual(result.returncode, 0, result.stderr)
        for index, section in enumerate(sections, 1):
            with self.subTest(artifact=index):
                self.assertEqual(
                    (self.output / f"artifact-{index}.patch").read_bytes(),
                    section.encode("utf-8"),
                )
        recorded = json.loads((self.output / "artifact-plan.json").read_text())
        self.assertEqual(recorded["artifacts"], artifacts)

    def test_preserves_unquoted_paths_and_numeric_artifact_keys(self):
        path = "src/caf\u00e9 with spaces.ts"
        section = self._section(path)
        self.diff.write_text(section, encoding="utf-8")
        self.plan.write_text(json.dumps({
            "artifacts": {"1": [path]},
            "lenses": {"reviewer": [1]},
        }))

        result = self._run("--plan", str(self.plan))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (self.output / "artifact-1.patch").read_bytes(),
            section.encode("utf-8"),
        )

    def test_uses_decoded_destination_path_for_rename(self):
        section = (
            'diff --git a/plain.ts "b/src/caf\\303\\251.ts"\n'
            "similarity index 100%\n"
            "rename from plain.ts\n"
            'rename to "src/caf\\303\\251.ts"\n'
        )
        self.diff.write_text(section)
        self.plan.write_text(json.dumps({
            "artifacts": {"artifact-1": ["src/caf\u00e9.ts"]},
        }))

        result = self._run("--plan", str(self.plan))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.output / "artifact-1.patch").read_text(), section)

    def test_list_reports_decoded_git_paths(self):
        self.diff.write_text(self._section(r"src/caf\303\251.ts", quoted=True))

        result = self._run("--list")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("src/caf\u00e9.ts", result.stdout)
        self.assertFalse(self.output.exists())

    def test_auto_plan_records_decoded_git_paths(self):
        section = self._section(r"src/caf\303\251.ts", quoted=True)
        self.diff.write_text(section)

        result = self._run("--auto", "2")

        self.assertEqual(result.returncode, 0, result.stderr)
        recorded = json.loads((self.output / "artifact-plan.json").read_text())
        self.assertEqual(recorded["artifacts"], {"1": ["src/caf\u00e9.ts"]})
        self.assertEqual((self.output / "artifact-1.patch").read_text(), section)

    def test_invalid_coverage_preserves_existing_artifacts_and_pinned_plan(self):
        for failure in ("unassigned", "unread"):
            with self.subTest(failure=failure):
                section = self._section("src/app.ts")
                if failure == "unassigned":
                    section += self._section("src/new.ts")
                self.diff.write_text(section)
                self.output.mkdir(exist_ok=True)
                self.plan = self.output / "artifact-plan.json"
                self.plan.write_text(json.dumps({
                    "artifacts": {"artifact-1": ["src/app.ts"]},
                    "lenses": {
                        "reviewer": ["artifact-2" if failure == "unread" else "artifact-1"],
                    },
                }, indent=2) + "\n")
                (self.output / "artifact-1.patch").write_text("Previous slice\n")
                (self.output / "artifact-2.patch").write_text("Unrelated slice\n")
                before = {path.name: path.read_bytes() for path in self.output.iterdir()}

                result = self._run("--plan", str(self.plan))

                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(
                    "assigned to NO artifact" if failure == "unassigned" else "read by no lens",
                    result.stderr,
                )
                self.assertEqual(
                    {path.name: path.read_bytes() for path in self.output.iterdir()},
                    before,
                )
                self.assertNotIn("wrote ", result.stdout)

    def test_invalid_coverage_does_not_create_output_directory(self):
        self.diff.write_text(self._section("src/app.ts") + self._section("src/new.ts"))
        self.plan.write_text(json.dumps({"artifacts": {"1": ["src/app.ts"]}}))

        result = self._run("--plan", str(self.plan))

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("assigned to NO artifact", result.stderr)
        self.assertFalse(self.output.exists())

    def test_fully_fixed_files_can_keep_empty_pinned_slices(self):
        section = self._section("src/app.ts")
        self.diff.write_text(section)
        self.plan.write_text(json.dumps({
            "artifacts": {
                "artifact-1": ["src/app.ts"],
                "artifact-2": ["src/fixed.ts"],
            },
            "lenses": {"reviewer": ["artifact-1", "artifact-2"]},
        }))
        self.output.mkdir()
        (self.output / "artifact-2.patch").write_text("Outdated slice\n")

        result = self._run("--plan", str(self.plan))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("paths absent from the diff", result.stderr)
        self.assertEqual((self.output / "artifact-1.patch").read_text(), section)
        self.assertEqual((self.output / "artifact-2.patch").read_bytes(), b"")


if __name__ == "__main__":
    unittest.main()
