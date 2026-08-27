#!/usr/bin/env python3

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SYNC_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SYNC_DIR / "remote-to-copilot.sh"


class RemoteToCopilotTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.fixture_sync = self.root / "tools/sync"
        (self.fixture_sync / "copilot").mkdir(parents=True)
        self.assertTrue(SCRIPT.exists(), "remote-to-copilot.sh must be implemented")
        shutil.copy2(SCRIPT, self.fixture_sync)
        self._write_executable(
            self.fixture_sync / "remote-to-workspace.sh",
            """
printf invoked > "$STUB_INSTALLER_LOG"
workspace="$1"
shift
if [ "${1:-}" = "--ref" ]; then
  [ "$2" != "installer-fail" ] || exit 17
  printf '%s' "$2" > "$STUB_REF_LOG"
fi
mkdir -p "$workspace/.claude/rules" "$workspace/.claude/agents" \
  "$workspace/.claude/skills"
printf '# Remote\n' > "$workspace/.claude/rules/remote.md"
""",
        )
        (self.fixture_sync / "copilot/generate.py").write_text(
            """
import os
from pathlib import Path
import sys

args = sys.argv[1:]
source = Path(args[args.index("--source") + 1])
target = Path(args[args.index("--target") + 1])
Path(os.environ["STUB_SOURCE_LOG"]).write_text(str(source))
if os.environ.get("STUB_GENERATOR_EXIT"):
    raise SystemExit(int(os.environ["STUB_GENERATOR_EXIT"]))
if "--dry-run" not in args and "--check" not in args:
    target.mkdir(parents=True, exist_ok=True)
    (target / "generated.md").write_text((source / "rules/remote.md").read_text())
print(" ".join(args))
"""
        )
        self.workspace = self.root / "work space"
        (self.workspace / ".github").mkdir(parents=True)
        self.source_log = self.root / "source.log"
        self.ref_log = self.root / "ref.log"
        self.installer_log = self.root / "installer.log"

    def tearDown(self):
        self.temporary.cleanup()

    def test_applies_directly_without_modifying_workspace_claude(self):
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (self.workspace / ".github/generated.md").read_text(), "# Remote\n"
        )
        self.assertFalse((self.workspace / ".claude").exists())
        staged_source = Path(self.source_log.read_text())
        self.assertFalse(staged_source.exists())

    def test_forwards_modes_and_ref_without_writing(self):
        for mode in ("--dry-run", "--check"):
            with self.subTest(mode=mode):
                generated = self.workspace / ".github/generated.md"
                generated.unlink(missing_ok=True)
                result = self._run(mode, "--ref", "v2026.08.22")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(mode, result.stdout)
                self.assertEqual(self.ref_log.read_text(), "v2026.08.22")
                self.assertFalse(generated.exists())
                self.assertFalse((self.workspace / ".claude").exists())

    def test_propagates_installer_and_generator_exit_status(self):
        installer = self._run("--ref", "installer-fail")
        self.assertEqual(installer.returncode, 17)
        generator = self._run(env={"STUB_GENERATOR_EXIT": "23"})
        self.assertEqual(generator.returncode, 23)

    def test_checks_python_before_downloading_remote_content(self):
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        self._write_executable(fake_bin / "python3", "exit 127\n")

        result = self._run(env={"PATH": f"{fake_bin}:{os.environ['PATH']}"})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("python3", result.stderr)
        self.assertFalse(self.installer_log.exists())

    def _run(self, *args, env=None):
        environment = os.environ.copy()
        environment["STUB_SOURCE_LOG"] = str(self.source_log)
        environment["STUB_REF_LOG"] = str(self.ref_log)
        environment["STUB_INSTALLER_LOG"] = str(self.installer_log)
        environment.update(env or {})
        return subprocess.run(
            [str(self.fixture_sync / "remote-to-copilot.sh"), str(self.workspace), *args],
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )

    def test_forwards_prune_to_generator(self):
        result = self._run("--prune")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--prune", result.stdout)

    def test_forwards_dry_run_and_prune_together(self):
        result = self._run("--dry-run", "--prune")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--dry-run", result.stdout)
        self.assertIn("--prune", result.stdout)

    def _write_executable(self, path, body):
        path.write_text(f"#!/usr/bin/env bash\nset -euo pipefail\n{body}")
        path.chmod(0o755)


if __name__ == "__main__":
    unittest.main()
