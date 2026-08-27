#!/usr/bin/env python3

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SYNC_DIR = Path(__file__).resolve().parent
if SYNC_DIR.name == "tests":
    SYNC_DIR = SYNC_DIR.parent
ROOT = SYNC_DIR.parents[1]
COPILOT_DIR = SYNC_DIR / "copilot"


class SyncFolderTest(unittest.TestCase):
    def test_production_shell_scripts_share_sync_folder(self):
        for name in (
            "sync.sh",
            "remote-to-workspace.sh",
            "workspace-to-checkout.sh",
            "remote-to-copilot.sh",
        ):
            self.assertTrue((SYNC_DIR / name).is_file(), name)
            self.assertFalse((ROOT / name).exists(), name)
        self.assertTrue((COPILOT_DIR / "generate.py").is_file())
        for retired in (
            "sdlc-skills.sh",
            "repo-to-claude.sh",
            "claude-to-repo.sh",
            "sync-skills.sh",
            "update-skills.sh",
            "contribute-skills.sh",
        ):
            self.assertFalse((SYNC_DIR / retired).exists(), retired)
        self.assertFalse((SYNC_DIR / "github").exists())
        self.assertFalse((ROOT / "tools/sync-github").exists())

    def test_dispatcher_routes_arguments_and_exit_codes(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary) / "repo with spaces"
            fixture_sync = fixture / "tools/sync"
            fixture_github = fixture_sync / "copilot"
            fixture_sync.mkdir(parents=True)
            fixture_github.mkdir(parents=True)
            shutil.copy2(SYNC_DIR / "sync.sh", fixture_sync)
            self._write_stub(
                fixture_sync / "remote-to-workspace.sh",
                '[ "${1:-}" != "--fail" ] || exit 17\n'
                'printf "remote-to-workspace:argc=%s\\n" "$#"\n'
                'index=0\n'
                'for argument in "$@"; do\n'
                '  printf "remote-to-workspace:arg[%s]=<%s>\\n" "$index" "$argument"\n'
                '  index=$((index + 1))\n'
                "done\n",
            )
            self._write_stub(
                fixture_sync / "workspace-to-checkout.sh",
                '[ "${1:-}" != "--fail" ] || exit 18\n'
                'printf "workspace-to-checkout:argc=%s\\n" "$#"\n'
                'for argument in "$@"; do printf "workspace-to-checkout:arg=<%s>\\n" "$argument"; done\n',
            )
            (fixture_github / "generate.py").write_text(
                'import sys\n'
                'if sys.argv[1:] == ["--fail"]:\n'
                '    sys.exit(19)\n'
                'print("workspace-to-copilot:" + " ".join(sys.argv[1:]))\n'
            )
            self._write_stub(
                fixture_sync / "remote-to-copilot.sh",
                '[ "${1:-}" != "--fail" ] || exit 20\n'
                'printf "remote-to-copilot:%s\\n" "$*"\n',
            )
            script = fixture_sync / "sync.sh"

            self.assertEqual(self._run(script, "help").returncode, 0)
            self.assertEqual(self._run(script).returncode, 2)
            self.assertEqual(self._run(script, "unknown").returncode, 2)
            self.assertEqual(
                self._run(
                    script,
                    "remote-to-workspace",
                    "/tmp/work space",
                    "--dry-run",
                    "--ref",
                    "v2026.06.01",
                    "--force",
                ).stdout.strip(),
                "remote-to-workspace:argc=5\n"
                "remote-to-workspace:arg[0]=</tmp/work space>\n"
                "remote-to-workspace:arg[1]=<--dry-run>\n"
                "remote-to-workspace:arg[2]=<--ref>\n"
                "remote-to-workspace:arg[3]=<v2026.06.01>\n"
                "remote-to-workspace:arg[4]=<--force>",
            )
            self.assertEqual(
                self._run(
                    script, "workspace-to-checkout", "/tmp/work space", "--dry-run"
                ).stdout.strip(),
                "workspace-to-checkout:argc=2\n"
                "workspace-to-checkout:arg=</tmp/work space>\n"
                "workspace-to-checkout:arg=<--dry-run>",
            )
            self.assertEqual(
                self._run(
                    script, "workspace-to-copilot", "/tmp/work space", "--check"
                ).stdout.strip(),
                "workspace-to-copilot:/tmp/work space --check",
            )
            self.assertEqual(
                self._run(
                    script, "remote-to-copilot", "/tmp/work space", "--ref", "v1"
                ).stdout.strip(),
                "remote-to-copilot:/tmp/work space --ref v1",
            )
            self.assertEqual(
                self._run(script, "remote-to-workspace", "--fail").returncode, 17
            )
            self.assertEqual(
                self._run(script, "workspace-to-checkout", "--fail").returncode, 18
            )
            self.assertEqual(
                self._run(script, "workspace-to-copilot", "--fail").returncode, 19
            )
            self.assertEqual(
                self._run(script, "remote-to-copilot", "--fail").returncode, 20
            )

            (fixture_sync / "workspace-to-checkout.sh").unlink()
            missing = self._run(script, "workspace-to-checkout")
            self.assertEqual(missing.returncode, 1)
            self.assertIn("missing implementation", missing.stderr)

    def test_contributor_resolves_repository_root_from_sync_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            clone = workspace / "repo"
            sync_dir = clone / "tools/sync"
            sync_dir.mkdir(parents=True)
            (clone / "skills").mkdir()
            (clone / "shared-manifest.txt").write_text("rules\n")
            (workspace / ".claude/rules").mkdir(parents=True)
            (workspace / ".claude/rules/base.md").write_text("# Base\n")
            shutil.copy2(
                SYNC_DIR / "workspace-to-checkout.sh", sync_dir
            )
            shutil.copy2(
                SYNC_DIR / "remote-to-workspace.sh", sync_dir
            )
            fake_bin = workspace / "bin"
            fake_bin.mkdir()
            self._write_stub(fake_bin / "rsync", "exit 0\n")

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            result = subprocess.run(
                [str(sync_dir / "workspace-to-checkout.sh"), "--dry-run"],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Already in sync", result.stdout)

    def _run(self, script, *args):
        return subprocess.run(
            [str(script), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def _write_stub(self, path, body):
        path.write_text(f"#!/usr/bin/env bash\nset -euo pipefail\n{body}")
        path.chmod(0o755)


if __name__ == "__main__":
    unittest.main()
