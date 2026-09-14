#!/usr/bin/env python3

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "remote-to-workspace.sh"


class RepoToClaudeTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self._write_executable(
            "curl",
            'output=""\n'
            'while [ "$#" -gt 0 ]; do\n'
            '  if [ "$1" = "-o" ]; then shift; output="$1"; fi\n'
            "  shift\n"
            "done\n"
            '[ -z "$output" ] || : > "$output"\n',
        )
        self._write_executable(
            "tar",
            'destination=""\n'
            'while [ "$#" -gt 0 ]; do\n'
            '  if [ "$1" = "-C" ]; then shift; destination="$1"; fi\n'
            "  shift\n"
            "done\n"
            'mkdir -p "$destination/rules" "$destination/agents" '
            '"$destination/scripts" "$destination/skills"\n'
            'mkdir -p "$destination/hooks/hooks"\n'
            'printf "# Base\\n" > "$destination/rules/base.md"\n'
            'printf "rules\\nagents\\nscripts\\nskills\\nHOW-TO-USE.md\\n" '
            '> "$destination/shared-manifest.txt"\n'
            'printf "# Guide\\n" > "$destination/HOW-TO-USE.md"\n'
            'printf "{}\\n" > "$destination/settings.local.json.example"\n'
            'printf "{}\\n" > "$destination/.mcp.json.example"\n'
            '[ -z "${INJECT_EXAMPLE_SYMLINK:-}" ] || { '
            'rm -f "$destination/$INJECT_EXAMPLE_NAME"; '
            'ln -s "$INJECT_EXAMPLE_SYMLINK" "$destination/$INJECT_EXAMPLE_NAME"; }\n'
            'printf "hook-settings\\n" > "$destination/hooks/settings.json"\n'
            'printf "#!/bin/sh\\necho block\\n" > "$destination/hooks/hooks/block-confidential.sh"\n'
            'chmod +x "$destination/hooks/hooks/block-confidential.sh"\n'
            '[ -z "${INJECT_HOOK_GUIDE:-}" ] || '
            'printf "# Remote hook guide\\n" '
            '> "$destination/hooks/hooks/HOW-TO-USE.md"\n'
            '[ -z "${INJECT_COLLIDING_HOOK_SETTINGS:-}" ] || '
            'printf "colliding hook settings\\n" '
            '> "$destination/hooks/hooks/settings.json"\n'
            '[ -z "${INJECT_HOOK_PARENT_SYMLINK:-}" ] || { '
            'mv "$destination/hooks" "$destination/hooks-real"; '
            'ln -s "$INJECT_HOOK_PARENT_SYMLINK" "$destination/hooks"; }\n'
            '[ -z "${INJECT_TOP_LEVEL_DANGLING_SYMLINK:-}" ] || { '
            'mv "$destination/rules" "$destination/rules-real"; '
            'ln -s "$INJECT_TOP_LEVEL_DANGLING_SYMLINK" "$destination/rules"; }\n'
            '[ -z "${INJECT_SOURCE_SYMLINK:-}" ] || '
            'ln -s /tmp/outside "$destination/rules/linked.md"\n'
            '[ -z "${INJECT_HOOK_SYMLINK:-}" ] || '
            'ln -s /tmp/outside "$destination/hooks/hooks/linked.sh"\n'
            # When INJECT_GLOB_MANIFEST is set, add a manifest line that contains
            # a glob metacharacter to test that set -f prevents CWD expansion.
            '[ -z "${INJECT_GLOB_MANIFEST:-}" ] || '
            'printf "rules[1]\\n" >> "$destination/shared-manifest.txt"\n'
            '[ -z "${INJECT_NESTED_MANIFEST:-}" ] || '
            'printf "nested/item\\n" >> "$destination/shared-manifest.txt"\n'
            '[ -z "${INJECT_OPTION_MANIFEST:-}" ] || '
            'printf "%s\\n" "-item" >> "$destination/shared-manifest.txt"\n'
            '[ -z "${INJECT_PROTECTED_MANIFEST:-}" ] || { '
            'printf "remote private settings\\n" > "$destination/settings.local.json"; '
            'printf "settings.local.json\\n" >> "$destination/shared-manifest.txt"; }\n'
            '[ -z "${INJECT_CASED_MANIFEST:-}" ] || '
            'printf "%s\\n" "$INJECT_CASED_MANIFEST" >> "$destination/shared-manifest.txt"\n'
            '[ -z "${INJECT_SKILLS_FILE:-}" ] || { '
            'rmdir "$destination/skills"; '
            'printf "not a skills directory\\n" > "$destination/skills"; }\n'
            '[ -z "${INJECT_LOCAL_SKILL_CASE:-}" ] || { '
            'mkdir -p "$destination/skills/$INJECT_LOCAL_SKILL_CASE"; '
            'printf "remote local skill\\n" '
            '> "$destination/skills/$INJECT_LOCAL_SKILL_CASE/private.md"; }\n'
            '[ -z "${INJECT_EMPTY_MANIFEST:-}" ] || '
            ': > "$destination/shared-manifest.txt"\n'
            '[ -z "${INJECT_UNTERMINATED_MANIFEST:-}" ] || '
            'printf "rules" > "$destination/shared-manifest.txt"\n'
            '[ -z "${INJECT_MANIFEST_DIRECTORY:-}" ] || { '
            'rm "$destination/shared-manifest.txt"; '
            'mkdir "$destination/shared-manifest.txt"; }\n'
            '[ -z "${INJECT_MANIFEST_SYMLINK:-}" ] || { '
            'mv "$destination/shared-manifest.txt" "$destination/shared-manifest-real.txt"; '
            'ln -s "$INJECT_MANIFEST_SYMLINK" "$destination/shared-manifest.txt"; }\n',
        )
        self._write_executable("gh", "printf '%040d\\n' 0\n")
        self.env = os.environ.copy()
        self.env["PATH"] = f"{self.bin}:{self.env['PATH']}"

    def tearDown(self):
        self.temporary.cleanup()

    def test_dry_run_leaves_fresh_workspace_untouched(self):
        workspace = self.root / "dry-run-workspace"
        workspace.mkdir()

        result = self._run(workspace, "--dry-run")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((workspace / ".claude").exists())
        self.assertFalse((workspace / ".mcp.json.example").exists())
        self.assertIn("would create CLAUDE.md", result.stdout)

    def test_dry_run_reports_mode_without_flag_suffix(self):
        workspace = self.root / "dry-run-mode-workspace"
        workspace.mkdir()

        result = self._run(workspace, "--dry-run")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Mode:      DRY-RUN (no changes written)\n", result.stdout)
        self.assertNotIn("DRY-RUN (no changes written)--dry-run", result.stdout)

    def test_dry_run_entrypoint_preview_uses_post_sync_rule_set(self):
        workspace = self.root / "dry-run-entrypoint-rules-workspace"
        rules = workspace / ".claude/rules"
        rules.mkdir(parents=True)
        (rules / "local.md").write_text("# Local\n")
        entrypoint = workspace / "CLAUDE.md"
        original = (
            "<!-- invocare-skills:begin (managed; do not edit inside) -->\n"
            "@.claude/rules/local.md\n"
            "<!-- invocare-skills:end -->\n"
        )
        entrypoint.write_text(original)

        result = self._run(workspace, "--dry-run")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("would refresh CLAUDE.md managed rules block", result.stdout)
        self.assertEqual(entrypoint.read_text(), original)
        self.assertFalse((rules / "base.md").exists())

    def test_dry_run_handles_rules_directory_without_markdown_files(self):
        for filename in (None, "notes.txt"):
            with self.subTest(existing_file=filename):
                workspace = self.root / f"dry-run-no-markdown-{filename}"
                rules = workspace / ".claude/rules"
                rules.mkdir(parents=True)
                if filename:
                    (rules / filename).write_text("Local notes\n")
                before = sorted(path.relative_to(workspace) for path in workspace.rglob("*"))

                result = self._run(workspace, "--dry-run")

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("would create CLAUDE.md", result.stdout)
                self.assertIn("[dry-run]", result.stdout)
                self.assertEqual(
                    sorted(path.relative_to(workspace) for path in workspace.rglob("*")),
                    before,
                )
                if filename:
                    self.assertEqual((rules / filename).read_text(), "Local notes\n")

    def test_stock_macos_bash_completes_fresh_dry_run(self):
        workspace = self.root / "bash-3-dry-run-workspace"
        workspace.mkdir()

        result = subprocess.run(
            ["/bin/bash", str(SCRIPT), str(workspace), "--dry-run"],
            capture_output=True,
            text=True,
            check=False,
            env=self.env,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("unbound variable", result.stderr)
        self.assertIn("[dry-run]", result.stdout)
        self.assertFalse((workspace / ".claude").exists())

    def test_stock_macos_bash_cleanup_preserves_failure_status(self):
        workspace = self.root / "bash-3-failure-workspace"
        workspace.mkdir()
        environment = dict(self.env)
        environment["INJECT_SOURCE_SYMLINK"] = "1"

        result = subprocess.run(
            ["/bin/bash", str(SCRIPT), str(workspace)],
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source symlink", result.stderr)
        self.assertFalse((workspace / ".claude").exists())

    def test_checks_cksum_before_writing_workspace(self):
        workspace = self.root / "missing-cksum-workspace"
        workspace.mkdir()
        self._write_executable("cksum", "exit 127\n")

        result = self._run(workspace)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cksum", result.stderr)
        self.assertFalse((workspace / ".claude").exists())

    # --- GNU rsync regression: dry-run hook destination must not need to exist ---

    def _run_with_gnu_rsync_guard(self, workspace, *args):
        """Run the installer with a wrapper that emulates GNU rsync's strict
        destination-existence check for --dry-run calls.

        GNU rsync exits with code 3 when the destination of a --dry-run transfer
        does not exist as a directory (trailing-slash source pattern).  macOS rsync
        is lenient and silently succeeds.  The wrapper delegates to the real rsync
        for all other invocations so we still exercise real rsync behaviour.
        """
        # Resolve the real rsync binary path NOW (before the wrapper shadows it).
        import shutil
        real_rsync = shutil.which("rsync") or "/usr/bin/rsync"
        wrapper_body = (
            '#!/usr/bin/env bash\n'
            'set -euo pipefail\n'
            '# Capture all args into an array so we can inspect them safely.\n'
            'args=("$@")\n'
            'dry=0\n'
            'for a in "${args[@]}"; do\n'
            '  [ "$a" = "--dry-run" ] && dry=1\n'
            'done\n'
            '# GNU rsync requires the destination DIRECTORY to already exist in dry-run\n'
            '# when the destination arg ends with / (directory-target pattern).\n'
            '# When the destination does not end with / rsync treats it as a file copy\n'
            '# and does not require the parent directory to exist.\n'
            'dest=""\n'
            'for a in "${args[@]}"; do\n'
            '  case "$a" in --*) ;; *) dest="$a" ;; esac\n'
            'done\n'
            'if [ "$dry" -eq 1 ]; then\n'
            '  case "$dest" in\n'
            '    */)\n'
            '      dest_clean="${dest%/}"\n'
            '      if [ -n "$dest_clean" ] && [ ! -d "$dest_clean" ]; then\n'
            '        printf "rsync: [receiver] mkdir \\"%s\\" failed: No such file or directory (2)\\n" "$dest_clean" >&2\n'
            '        echo "rsync error: error in file IO (code 11) at receiver.c(819) [receiver=3.x]" >&2\n'
            '        exit 3\n'
            '      fi\n'
            '    ;;\n'
            '  esac\n'
            'fi\n'
            f'exec "{real_rsync}" "$@"\n'
        )
        # Write a temporary rsync wrapper that shadows the system rsync for this run only.
        gnu_bin = self.root / "gnu-bin"
        gnu_bin.mkdir(exist_ok=True)
        rsync_wrapper = gnu_bin / "rsync"
        rsync_wrapper.write_text(wrapper_body)
        rsync_wrapper.chmod(0o755)
        env = dict(self.env)
        env["PATH"] = f"{gnu_bin}:{env['PATH']}"
        return subprocess.run(
            [str(SCRIPT), str(workspace), *args],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )

    def test_dry_run_fresh_workspace_succeeds_under_gnu_rsync(self):
        """Dry-run on a fresh workspace must not fail with code 3 on GNU rsync.

        GNU rsync exits code 3 when a trailing-slash-source rsync targets a
        nonexistent destination directory.  The fix must redirect the hook rsync
        to a shadow dir under $TMP so the real destination is never required.
        """
        workspace = self.root / "gnu-dry-run-fresh"
        workspace.mkdir()

        result = self._run_with_gnu_rsync_guard(workspace, "--dry-run")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((workspace / ".claude").exists(),
                         "dry-run must not create .claude in the workspace")
        self.assertFalse((workspace / ".mcp.json.example").exists())

    def test_dry_run_claude_present_hooks_absent_succeeds_under_gnu_rsync(self):
        """Dry-run with .claude/ present but .claude/hooks/ absent must also succeed.

        This exercises the case where a workspace already has .claude/ (e.g. a
        partial install) but .claude/hooks/ has not been created yet.
        """
        workspace = self.root / "gnu-dry-run-partial"
        workspace.mkdir()
        (workspace / ".claude").mkdir()

        result = self._run_with_gnu_rsync_guard(workspace, "--dry-run")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((workspace / ".claude/hooks").exists(),
                         "dry-run must not create .claude/hooks")

    def test_dry_run_type_conflict_succeeds_under_gnu_rsync(self):
        workspace = self.root / "gnu-dry-run-type-conflict"
        workspace.mkdir()
        first = self._run(workspace)
        self.assertEqual(first.returncode, 0, first.stderr)
        rule = workspace / ".claude/rules/base.md"
        rule.unlink()
        rule.mkdir()
        local = rule / "local.txt"
        local.write_text("keep me\n")
        local.chmod(0)

        result = self._run_with_gnu_type_conflict_guard(
            workspace, "--dry-run"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("would back up type conflict", result.stdout)
        self.assertTrue(local.exists())
        self.assertEqual(local.stat().st_mode & 0o777, 0)

    def test_dry_run_treats_unreadable_same_type_file_as_updated(self):
        workspace = self.root / "dry-run-unreadable-file"
        workspace.mkdir()
        first = self._run(workspace)
        self.assertEqual(first.returncode, 0, first.stderr)
        rule = workspace / ".claude/rules/base.md"
        rule.chmod(0)
        try:
            result = self._run(workspace, "--dry-run", "--force")
        finally:
            rule.chmod(0o600)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("would update unreadable file: rules/base.md", result.stdout)
        self.assertIn("updated  rules/base.md", result.stdout)

    def test_dry_run_reports_file_permission_changes_without_writing(self):
        workspace = self.root / "dry-run-permission-workspace"
        workspace.mkdir()
        first = self._run(workspace)
        self.assertEqual(first.returncode, 0, first.stderr)
        rule = workspace / ".claude/rules/base.md"
        rule.chmod(0o600)

        preview = self._run(workspace, "--dry-run", "--force")

        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertIn("metadata rules/base.md", preview.stdout)
        self.assertNotIn("nothing to do", preview.stdout)
        self.assertEqual(rule.stat().st_mode & 0o777, 0o600)

    def test_dry_run_reports_directory_permission_changes_without_writing(self):
        workspace = self.root / "dry-run-directory-permission-workspace"
        workspace.mkdir()
        first = self._run(workspace)
        self.assertEqual(first.returncode, 0, first.stderr)
        rules = workspace / ".claude/rules"
        rules.chmod(0o700)

        preview = self._run(workspace, "--dry-run", "--force")

        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertIn("metadata rules/", preview.stdout)
        self.assertNotIn("nothing to do", preview.stdout)
        self.assertEqual(rules.stat().st_mode & 0o777, 0o700)

    def test_forced_dry_run_does_not_report_unchanged_hook_settings(self):
        workspace = self.root / "unchanged-hook-settings-workspace"
        workspace.mkdir()
        first = self._run(workspace)
        self.assertEqual(first.returncode, 0, first.stderr)

        preview = self._run(workspace, "--dry-run", "--force")

        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertNotIn("updated  settings.json", preview.stdout)
        self.assertIn(".claude/ is already current", preview.stdout)

    def test_dry_run_example_only_change_is_not_summarized_as_current(self):
        workspace = self.root / "dry-run-example-only-workspace"
        workspace.mkdir()
        first = self._run(workspace)
        self.assertEqual(first.returncode, 0, first.stderr)
        example = workspace / ".mcp.json.example"
        example.unlink()

        preview = self._run(workspace, "--dry-run", "--force")

        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertIn("would create .mcp.json.example", preview.stdout)
        self.assertNotIn("nothing to do", preview.stdout)
        self.assertFalse(example.exists())

    def test_apply_installs_configuration_examples_at_target_levels(self):
        workspace = self.root / "apply-workspace"
        workspace.mkdir()

        result = self._run(workspace)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((workspace / ".claude/settings.local.json.example").is_file())
        self.assertTrue((workspace / ".mcp.json.example").is_file())

    def test_apply_preserves_existing_configuration_examples(self):
        workspace = self.root / "existing-examples-workspace"
        (workspace / ".claude").mkdir(parents=True)
        settings_example = workspace / ".claude/settings.local.json.example"
        mcp_example = workspace / ".mcp.json.example"
        settings_example.write_text("local settings\n")
        mcp_example.write_text("local mcp\n")

        result = self._run(workspace)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(settings_example.read_text(), "local settings\n")
        self.assertEqual(mcp_example.read_text(), "local mcp\n")

    def test_backup_directory_cannot_redirect_writes_through_predictable_symlink(self):
        workspace = self.root / "backup-symlink-workspace"
        rule = workspace / ".claude/rules/base.md"
        rule.parent.mkdir(parents=True)
        rule.write_text("# Local\n")
        outside = self.root / "outside-backups"
        outside.mkdir()
        timestamp = "20260827-225304"
        (workspace / f".claude/.update-backup-{timestamp}").symlink_to(
            outside, target_is_directory=True
        )
        self._write_executable("date", f"printf '{timestamp}\\n'\n")

        result = self._run(workspace)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((outside / "rules/base.md").exists())
        backups = list(
            (workspace / ".claude").glob(f".update-backup-{timestamp}.*")
        )
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "rules/base.md").read_text(), "# Local\n")

    def test_backup_output_handles_workspace_glob_characters(self):
        workspace = self.root / "work[abc]"
        rule = workspace / ".claude/rules/base.md"
        rule.parent.mkdir(parents=True)
        rule.write_text("# Local\n")

        result = self._run(workspace)

        self.assertEqual(result.returncode, 0, result.stderr)
        backup_line = next(
            line for line in result.stdout.splitlines()
            if "Replaced files were backed up to:" in line
        )
        self.assertIn(".claude/.update-backup-", backup_line)
        self.assertNotIn(str(workspace), backup_line)

    def test_root_and_hook_backups_use_distinct_relative_paths(self):
        workspace = self.root / "distinct-backup-workspace"
        root_guide = workspace / ".claude/HOW-TO-USE.md"
        hook_guide = workspace / ".claude/hooks/HOW-TO-USE.md"
        hook_guide.parent.mkdir(parents=True)
        root_guide.write_text("# Local root guide\n")
        hook_guide.write_text("# Local hook guide\n")
        self.env["INJECT_HOOK_GUIDE"] = "1"

        result = self._run(workspace)

        self.assertEqual(result.returncode, 0, result.stderr)
        backups = list((workspace / ".claude").glob(".update-backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(
            (backups[0] / "HOW-TO-USE.md").read_text(),
            "# Local root guide\n",
        )
        self.assertEqual(
            (backups[0] / "hooks/HOW-TO-USE.md").read_text(),
            "# Local hook guide\n",
        )

    def test_rejects_unsafe_remote_ref(self):
        workspace = self.root / "unsafe-ref-workspace"
        workspace.mkdir()

        result = self._run(workspace, "--ref", "--upload-pack=bad")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid ref", result.stderr)
        self.assertFalse((workspace / ".claude").exists())

    def test_rejects_remote_ref_with_parent_segments(self):
        workspace = self.root / "parent-ref-workspace"
        workspace.mkdir()

        result = self._run(workspace, "--ref", "branch/../../other-repo")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid ref", result.stderr)
        self.assertFalse((workspace / ".claude").exists())

    def test_rejects_multiple_workspace_paths(self):
        workspace = self.root / "first-workspace"
        other = self.root / "second-workspace"
        workspace.mkdir()
        other.mkdir()

        result = self._run(workspace, str(other))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("only one workspace path", result.stderr)
        self.assertFalse((workspace / ".claude").exists())
        self.assertFalse((other / ".claude").exists())

    def test_relative_workspace_ignores_exported_cdpath(self):
        invocation = self.root / "invocation"
        cdpath = self.root / "cdpath"
        workspace = invocation / "workspace"
        decoy = cdpath / "workspace"
        workspace.mkdir(parents=True)
        decoy.mkdir(parents=True)
        environment = dict(self.env)
        environment["CDPATH"] = str(cdpath)

        result = subprocess.run(
            [str(SCRIPT), "workspace"],
            cwd=invocation,
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((workspace / ".claude/rules/base.md").is_file())
        self.assertFalse((decoy / ".claude").exists())

    def test_empty_workspace_argument_still_counts_as_a_positional_path(self):
        workspace = self.root / "empty-argument-workspace"
        workspace.mkdir()

        result = subprocess.run(
            [str(SCRIPT), "", str(workspace)],
            capture_output=True,
            text=True,
            check=False,
            env=self.env,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("only one workspace path", result.stderr)
        self.assertFalse((workspace / ".claude").exists())

    def test_migrates_legacy_managed_block_without_losing_user_content(self):
        workspace = self.root / "legacy-marker-workspace"
        workspace.mkdir()
        (workspace / "CLAUDE.md").write_text(
            "<!-- invocare-skills:begin (managed by update-skills.sh — do not edit inside) -->\n"
            "@.claude/rules/old.md\n"
            "<!-- invocare-skills:end -->\n\n"
            "# Local guidance\n"
        )

        result = self._run(workspace)

        self.assertEqual(result.returncode, 0, result.stderr)
        content = (workspace / "CLAUDE.md").read_text()
        self.assertIn("invocare-skills:begin (managed; do not edit inside)", content)
        self.assertNotIn("managed by update-skills.sh", content)
        self.assertEqual(content.count("invocare-skills:begin"), 1)
        self.assertIn("# Local guidance", content)

    def test_root_entrypoint_update_ignores_preexisting_fixed_temp_symlink(self):
        workspace = self.root / "entrypoint-temp-symlink-workspace"
        workspace.mkdir()
        entrypoint = workspace / "CLAUDE.md"
        entrypoint.write_text(
            "<!-- invocare-skills:begin (managed; do not edit inside) -->\n"
            "@.claude/rules/old.md\n"
            "<!-- invocare-skills:end -->\n\n"
            "# Local guidance\n"
        )
        outside = self.root / "outside-entrypoint.md"
        outside.write_text("keep me\n")
        (workspace / "CLAUDE.md.tmp").symlink_to(outside)

        result = self._run(workspace)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(outside.read_text(), "keep me\n")
        self.assertFalse(entrypoint.is_symlink())
        self.assertIn("# Local guidance", entrypoint.read_text())

    def test_root_entrypoint_update_preserves_existing_permissions(self):
        workspace = self.root / "entrypoint-permissions-workspace"
        workspace.mkdir()
        entrypoint = workspace / "CLAUDE.md"
        entrypoint.write_text("# Local guidance\n")
        entrypoint.chmod(0o600)

        result = self._run(workspace)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(entrypoint.stat().st_mode & 0o777, 0o600)

    def test_gnu_stat_mode_probe_ignores_percent_lp_path(self):
        workspace = self.root / "gnu-stat-workspace"
        workspace.mkdir()
        entrypoint = workspace / "CLAUDE.md"
        entrypoint.write_text("# Local guidance\n")
        entrypoint.chmod(0o600)
        invocation = self.root / "gnu-stat-invocation"
        invocation.mkdir()
        (invocation / "%Lp").write_text("decoy\n")
        self._write_executable(
            "stat",
            'case "${1:-}" in\n'
            '  -c) printf "600\\n"; exit 0 ;;\n'
            '  -f) [ -e "%Lp" ] || exit 1; printf "gnu operand output\\n"; exit 0 ;;\n'
            'esac\n'
            'exit 1\n',
        )

        result = subprocess.run(
            [str(SCRIPT), str(workspace)],
            cwd=invocation,
            capture_output=True,
            text=True,
            check=False,
            env=self.env,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("invocare-skills:begin", entrypoint.read_text())
        self.assertEqual(entrypoint.stat().st_mode & 0o777, 0o600)

    def test_short_octal_file_mode_is_accepted(self):
        workspace = self.root / "short-mode-workspace"
        workspace.mkdir()
        entrypoint = workspace / "CLAUDE.md"
        entrypoint.write_text("# Local guidance\n")
        self._write_executable(
            "stat",
            'case "${1:-}" in\n'
            '  -c) printf "4\\n"; exit 0 ;;\n'
            'esac\n'
            'exit 1\n',
        )

        result = self._run(workspace)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(entrypoint.stat().st_mode & 0o777, 0o004)

    def test_read_only_root_entrypoint_updates_without_partial_install(self):
        workspace = self.root / "read-only-entrypoint-workspace"
        workspace.mkdir()
        entrypoint = workspace / "CLAUDE.md"
        entrypoint.write_text("# Local guidance\n")
        entrypoint.chmod(0o444)
        self._install_mv_prompt_guard()

        result = self._run(workspace)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(entrypoint.stat().st_mode & 0o777, 0o444)
        self.assertIn("# Local guidance", entrypoint.read_text())
        self.assertIn("invocare-skills:begin", entrypoint.read_text())

    def test_new_root_entrypoint_honors_restrictive_umask(self):
        workspace = self.root / "entrypoint-umask-workspace"
        workspace.mkdir()

        result = subprocess.run(
            [
                "bash",
                "-c",
                'umask 077; exec "$@"',
                "installer",
                str(SCRIPT),
                str(workspace),
            ],
            capture_output=True,
            text=True,
            check=False,
            env=self.env,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (workspace / "CLAUDE.md").stat().st_mode & 0o777,
            0o600,
        )

    def test_rejects_entrypoint_directory_before_writing_workspace(self):
        workspace = self.root / "entrypoint-directory-workspace"
        (workspace / "CLAUDE.md").mkdir(parents=True)

        result = self._run(workspace)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CLAUDE.md must be a file", result.stderr)
        self.assertFalse((workspace / ".claude").exists())

    def test_rejects_unreadable_entrypoint_before_writing_workspace(self):
        workspace = self.root / "unreadable-entrypoint-workspace"
        workspace.mkdir()
        entrypoint = workspace / "CLAUDE.md"
        entrypoint.write_text("# Private\n")
        entrypoint.chmod(0)
        try:
            result = self._run(workspace)
        finally:
            entrypoint.chmod(0o600)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CLAUDE.md is not readable", result.stderr)
        self.assertFalse((workspace / ".claude").exists())

    def test_malformed_marker_order_preserves_all_user_content(self):
        workspace = self.root / "malformed-marker-order-workspace"
        workspace.mkdir()
        entrypoint = workspace / "CLAUDE.md"
        entrypoint.write_text(
            "<!-- invocare-skills:end -->\n"
            "# Content before malformed begin\n"
            "<!-- invocare-skills:begin (managed; do not edit inside) -->\n"
            "@.claude/rules/old.md\n"
            "# Content after malformed begin must survive\n"
        )

        result = self._run(workspace)

        self.assertEqual(result.returncode, 0, result.stderr)
        content = entrypoint.read_text()
        self.assertIn("# Content before malformed begin", content)
        self.assertIn("# Content after malformed begin must survive", content)
        self.assertIn("@.claude/rules/base.md", content)
        begin_count = content.count("invocare-skills:begin")
        end_count = content.count("invocare-skills:end")

        repeated = self._run(workspace, "--force")

        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        repeated_content = entrypoint.read_text()
        self.assertEqual(
            repeated_content.count("invocare-skills:begin"),
            begin_count,
        )
        self.assertEqual(
            repeated_content.count("invocare-skills:end"),
            end_count,
        )
        self.assertIn(
            "# Content after malformed begin must survive",
            repeated_content,
        )

    def test_nested_managed_begin_marker_does_not_consume_user_content(self):
        workspace = self.root / "nested-marker-workspace"
        workspace.mkdir()
        entrypoint = workspace / "CLAUDE.md"
        entrypoint.write_text(
            "<!-- invocare-skills:begin (managed; do not edit inside) -->\n"
            "# Content between markers must survive\n"
            "<!-- invocare-skills:begin (managed by update-skills.sh — do not edit inside) -->\n"
            "@.claude/rules/old.md\n"
            "# Inner content must survive\n"
            "<!-- invocare-skills:end -->\n"
            "# Content after managed block\n"
        )

        result = self._run(workspace)

        self.assertEqual(result.returncode, 0, result.stderr)
        content = entrypoint.read_text()
        self.assertIn("# Content between markers must survive", content)
        self.assertIn("# Inner content must survive", content)
        self.assertIn("# Content after managed block", content)
        self.assertIn("@.claude/rules/base.md", content)

    def test_preserves_user_content_when_managed_end_marker_is_missing(self):
        workspace = self.root / "missing-end-marker-workspace"
        workspace.mkdir()
        (workspace / "CLAUDE.md").write_text(
            "<!-- invocare-skills:begin (managed; do not edit inside) -->\n"
            "@.claude/rules/old.md\n"
            "# Local guidance must survive\n"
        )

        result = self._run(workspace)

        self.assertEqual(result.returncode, 0, result.stderr)
        content = (workspace / "CLAUDE.md").read_text()
        self.assertIn("# Local guidance must survive", content)
        self.assertIn("@.claude/rules/base.md", content)

        repeated = self._run(workspace, "--force")

        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        content = (workspace / "CLAUDE.md").read_text()
        self.assertIn("# Local guidance must survive", content)

    def test_tracks_remote_state_and_restores_missing_files(self):
        workspace = self.root / "state-workspace"
        workspace.mkdir()

        first = self._run(workspace)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertTrue((workspace / ".claude/.skills-sync-state").is_file())
        self.assertTrue((workspace / ".claude/.skills-sync-manifest").is_file())

        second = self._run(workspace)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("Already up to date", second.stdout)

        installed_rule = workspace / ".claude/rules/base.md"
        installed_rule.unlink()
        restored = self._run(workspace)
        self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assertTrue(installed_rule.is_file())
        self.assertIn("missing locally", restored.stdout)

        forced = self._run(workspace, "--force")
        self.assertEqual(forced.returncode, 0, forced.stderr)
        self.assertIn("Downloading latest skill set", forced.stdout)

    def test_corrupt_sync_manifest_forces_reinstall_and_repairs_tracking(self):
        workspace = self.root / "corrupt-manifest-workspace"
        workspace.mkdir()

        first = self._run(workspace)
        self.assertEqual(first.returncode, 0, first.stderr)
        manifest = workspace / ".claude/.skills-sync-manifest"
        expected_entries = manifest.read_text().splitlines()
        self.assertGreater(len(expected_entries), 1)
        manifest.write_text(expected_entries[0] + "\n")

        repaired = self._run(workspace)

        self.assertEqual(repaired.returncode, 0, repaired.stderr)
        self.assertNotIn("Already up to date", repaired.stdout)
        self.assertIn("Downloading latest skill set", repaired.stdout)
        self.assertEqual(set(manifest.read_text().splitlines()), set(expected_entries))

    def test_same_size_manifest_reordering_forces_reinstall(self):
        workspace = self.root / "reordered-manifest-workspace"
        workspace.mkdir()

        first = self._run(workspace)
        self.assertEqual(first.returncode, 0, first.stderr)
        manifest = workspace / ".claude/.skills-sync-manifest"
        expected_entries = manifest.read_text().splitlines()
        self.assertGreater(len(expected_entries), 1)
        manifest.write_text("\n".join(reversed(expected_entries)) + "\n")

        repaired = self._run(workspace)

        self.assertEqual(repaired.returncode, 0, repaired.stderr)
        self.assertIn("Downloading latest skill set", repaired.stdout)
        self.assertEqual(manifest.read_text().splitlines(), expected_entries)

    def test_legacy_two_field_sync_state_is_upgraded(self):
        workspace = self.root / "legacy-state-workspace"
        workspace.mkdir()

        first = self._run(workspace)
        self.assertEqual(first.returncode, 0, first.stderr)
        state = workspace / ".claude/.skills-sync-state"
        legacy_fields = state.read_text().split()[:2]
        state.write_text(" ".join(legacy_fields) + "\n")

        upgraded = self._run(workspace)

        self.assertEqual(upgraded.returncode, 0, upgraded.stderr)
        self.assertIn("Downloading latest skill set", upgraded.stdout)
        self.assertEqual(len(state.read_text().split()), 4)

    def test_read_only_corrupt_manifest_is_atomically_repaired(self):
        workspace = self.root / "read-only-manifest-workspace"
        workspace.mkdir()

        first = self._run(workspace)
        self.assertEqual(first.returncode, 0, first.stderr)
        manifest = workspace / ".claude/.skills-sync-manifest"
        expected_entries = manifest.read_text().splitlines()
        manifest.write_text(expected_entries[0] + "\n")
        manifest.chmod(0o444)
        self._install_mv_prompt_guard()

        repaired = self._run(workspace)

        self.assertEqual(repaired.returncode, 0, repaired.stderr)
        self.assertEqual(
            set(manifest.read_text().splitlines()),
            set(expected_entries),
        )
        current = self._run(workspace)
        self.assertEqual(current.returncode, 0, current.stderr)
        self.assertIn("Already up to date", current.stdout)

    def test_restores_missing_workspace_entrypoint_without_force(self):
        workspace = self.root / "missing-entrypoint-workspace"
        workspace.mkdir()

        first = self._run(workspace)
        self.assertEqual(first.returncode, 0, first.stderr)
        entrypoint = workspace / "CLAUDE.md"
        entrypoint.unlink()

        restored = self._run(workspace)

        self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assertNotIn("Already up to date", restored.stdout)
        self.assertIn("missing locally", restored.stdout)
        self.assertIn("invocare-skills:begin", entrypoint.read_text())

    def test_refreshes_workspace_entrypoint_when_local_rule_is_added(self):
        workspace = self.root / "local-rule-entrypoint-workspace"
        workspace.mkdir()
        first = self._run(workspace)
        self.assertEqual(first.returncode, 0, first.stderr)
        local_rule = workspace / ".claude/rules/local.md"
        local_rule.write_text("# Local rule\n")

        refreshed = self._run(workspace)

        self.assertEqual(refreshed.returncode, 0, refreshed.stderr)
        self.assertNotIn("Already up to date", refreshed.stdout)
        self.assertNotIn("nothing changed", refreshed.stdout)
        self.assertIn(
            "@.claude/rules/local.md",
            (workspace / "CLAUDE.md").read_text(),
        )

    def test_dry_run_previews_local_rule_entrypoint_refresh_at_same_commit(self):
        workspace = self.root / "dry-run-local-rule-entrypoint-workspace"
        workspace.mkdir()
        first = self._run(workspace)
        self.assertEqual(first.returncode, 0, first.stderr)
        entrypoint = workspace / "CLAUDE.md"
        original = entrypoint.read_text()
        (workspace / ".claude/rules/local.md").write_text("# Local rule\n")

        preview = self._run(workspace, "--dry-run")

        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertIn("CLAUDE.md needs refresh", preview.stdout)
        self.assertIn("would refresh CLAUDE.md managed rules block", preview.stdout)
        self.assertNotIn("nothing to do", preview.stdout)
        self.assertEqual(entrypoint.read_text(), original)

    def test_restores_tracked_files_replaced_by_symlinks_or_directories(self):
        replacements = ("symlink", "directory")
        for index, replacement in enumerate(replacements):
            with self.subTest(replacement=replacement):
                workspace = self.root / f"invalid-tracked-file-{index}"
                workspace.mkdir()
                first = self._run(workspace)
                self.assertEqual(first.returncode, 0, first.stderr)
                rule = workspace / ".claude/rules/base.md"
                rule.unlink()
                if replacement == "symlink":
                    outside = self.root / f"outside-tracked-file-{index}"
                    outside.write_text("# Outside\n")
                    rule.symlink_to(outside)
                else:
                    rule.mkdir()

                restored = self._run(workspace)

                self.assertEqual(restored.returncode, 0, restored.stderr)
                self.assertIn("missing locally", restored.stdout)
                self.assertTrue(rule.is_file())
                self.assertFalse(rule.is_symlink())

    def test_restores_managed_path_with_symlinked_ancestor(self):
        workspace = self.root / "managed-ancestor-symlink-workspace"
        workspace.mkdir()
        first = self._run(workspace)
        self.assertEqual(first.returncode, 0, first.stderr)
        rules = workspace / ".claude/rules"
        outside = self.root / "outside-managed-rules"
        rules.rename(outside)
        rules.symlink_to(outside, target_is_directory=True)

        restored = self._run(workspace)

        self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assertIn("missing locally", restored.stdout)
        self.assertFalse(rules.is_symlink())
        self.assertTrue((rules / "base.md").is_file())
        self.assertTrue((outside / "base.md").is_file())

    def test_type_conflicts_are_backed_up_before_restoration(self):
        workspace = self.root / "type-conflict-workspace"
        workspace.mkdir()
        first = self._run(workspace)
        self.assertEqual(first.returncode, 0, first.stderr)

        rule = workspace / ".claude/rules/base.md"
        rule.unlink()
        rule.mkdir()
        (rule / "local.txt").write_text("local directory content\n")
        file_conflict = self._run(workspace)

        self.assertEqual(file_conflict.returncode, 0, file_conflict.stderr)
        self.assertTrue(rule.is_file())
        file_backups = list(
            (workspace / ".claude").glob(
                ".update-backup-*/rules/base.md/local.txt"
            )
        )
        self.assertEqual(len(file_backups), 1)
        self.assertEqual(file_backups[0].read_text(), "local directory content\n")

        rules = workspace / ".claude/rules"
        rule.unlink()
        rules.rmdir()
        rules.write_text("local file content\n")
        directory_conflict = self._run(workspace)

        self.assertEqual(
            directory_conflict.returncode,
            0,
            directory_conflict.stderr,
        )
        self.assertTrue(rules.is_dir())
        directory_backups = [
            path
            for path in (workspace / ".claude").glob(
                ".update-backup-*/rules"
            )
            if path.is_file()
        ]
        self.assertEqual(len(directory_backups), 1)
        self.assertEqual(directory_backups[0].read_text(), "local file content\n")

    def test_dry_run_previews_type_conflict_without_modifying_workspace(self):
        workspace = self.root / "dry-run-type-conflict-workspace"
        workspace.mkdir()
        first = self._run(workspace)
        self.assertEqual(first.returncode, 0, first.stderr)
        rule = workspace / ".claude/rules/base.md"
        rule.unlink()
        rule.mkdir()
        local = rule / "local.txt"
        local.write_text("keep me\n")

        preview = self._run(workspace, "--dry-run")

        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertIn("type conflict", preview.stdout)
        self.assertTrue(rule.is_dir())
        self.assertEqual(local.read_text(), "keep me\n")

    def test_dry_run_empty_directory_conflict_is_not_summarized_as_current(self):
        workspace = self.root / "dry-run-empty-directory-conflict"
        workspace.mkdir()
        first = self._run(workspace)
        self.assertEqual(first.returncode, 0, first.stderr)
        agents = workspace / ".claude/agents"
        agents.rmdir()
        agents.write_text("local conflict\n")

        preview = self._run(workspace, "--dry-run", "--force")

        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertIn("would back up type conflict: agents", preview.stdout)
        self.assertNotIn("nothing to do", preview.stdout)
        self.assertEqual(agents.read_text(), "local conflict\n")

    def test_replaces_workspace_entrypoint_symlink_without_touching_target(self):
        workspace = self.root / "entrypoint-symlink-restore-workspace"
        workspace.mkdir()
        first = self._run(workspace)
        self.assertEqual(first.returncode, 0, first.stderr)
        entrypoint = workspace / "CLAUDE.md"
        entrypoint.unlink()
        outside = self.root / "outside-entrypoint-target.md"
        outside.write_text("# Outside\n")
        entrypoint.symlink_to(outside)

        restored = self._run(workspace)

        self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assertIn("missing locally", restored.stdout)
        self.assertFalse(entrypoint.is_symlink())
        self.assertEqual(outside.read_text(), "# Outside\n")

    def test_dry_run_previews_workspace_entrypoint_symlink_replacement(self):
        workspace = self.root / "entrypoint-symlink-preview-workspace"
        workspace.mkdir()
        first = self._run(workspace)
        self.assertEqual(first.returncode, 0, first.stderr)
        entrypoint = workspace / "CLAUDE.md"
        entrypoint.unlink()
        outside = self.root / "outside-entrypoint-preview.md"
        outside.write_text("# Outside\n")
        entrypoint.symlink_to(outside)

        preview = self._run(workspace, "--dry-run")

        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertIn("would replace CLAUDE.md symlink", preview.stdout)
        self.assertNotIn("nothing to do", preview.stdout)
        self.assertTrue(entrypoint.is_symlink())
        self.assertEqual(outside.read_text(), "# Outside\n")

    def test_rejects_symlinks_in_remote_payload(self):
        workspace = self.root / "symlink-workspace"
        workspace.mkdir()
        self.env["INJECT_SOURCE_SYMLINK"] = "1"

        result = self._run(workspace)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source symlink", result.stderr)
        self.assertFalse((workspace / ".claude").exists())

    def test_rejects_symlinked_remote_configuration_examples(self):
        outside = self.root / "private-example-source"
        outside.write_text("private\n")
        for index, filename in enumerate(
            ("settings.local.json.example", ".mcp.json.example")
        ):
            with self.subTest(filename=filename):
                workspace = self.root / f"source-example-symlink-{index}"
                workspace.mkdir()
                self.env["INJECT_EXAMPLE_SYMLINK"] = str(outside)
                self.env["INJECT_EXAMPLE_NAME"] = filename

                result = self._run(workspace)

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("source symlink", result.stderr)
                self.assertFalse((workspace / ".claude").exists())
                self.assertFalse((workspace / filename).exists())

    def test_rejects_symlinked_remote_hooks_parent(self):
        workspace = self.root / "source-hooks-parent-symlink"
        workspace.mkdir()
        outside = self.root / "outside-hooks-source"
        (outside / "hooks").mkdir(parents=True)
        (outside / "hooks/block-confidential.sh").write_text("#!/bin/sh\n")
        (outside / "settings.json").write_text("outside settings\n")
        self.env["INJECT_HOOK_PARENT_SYMLINK"] = str(outside)

        result = self._run(workspace)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source symlink", result.stderr)
        self.assertFalse((workspace / ".claude").exists())

    def test_rejects_manifest_listed_dangling_top_level_symlink(self):
        workspace = self.root / "source-top-level-dangling-symlink"
        workspace.mkdir()
        self.env["INJECT_TOP_LEVEL_DANGLING_SYMLINK"] = str(
            self.root / "missing-rules-source"
        )

        result = self._run(workspace)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source symlink", result.stderr)
        self.assertFalse((workspace / ".claude").exists())

    def test_rejects_symlinked_claude_destination_without_writing_outside(self):
        workspace = self.root / "symlinked-claude-workspace"
        outside = self.root / "outside-claude"
        workspace.mkdir()
        outside.mkdir()
        (workspace / ".claude").symlink_to(outside, target_is_directory=True)

        result = self._run(workspace)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("destination symlink", result.stderr)
        self.assertFalse((outside / "rules/base.md").exists())

    def test_rejects_symlinked_hooks_destination_without_writing_outside(self):
        workspace = self.root / "symlinked-hooks-workspace"
        outside = self.root / "outside-hooks"
        (workspace / ".claude").mkdir(parents=True)
        outside.mkdir()
        (workspace / ".claude/hooks").symlink_to(
            outside, target_is_directory=True
        )

        result = self._run(workspace)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("destination symlink", result.stderr)
        self.assertFalse((outside / "block-confidential.sh").exists())

    def test_rejects_symlinked_hook_settings_directory_without_writing_outside(self):
        workspace = self.root / "symlinked-hook-settings-workspace"
        outside = self.root / "outside-hook-settings"
        (workspace / ".claude/hooks").mkdir(parents=True)
        outside.mkdir()
        (workspace / ".claude/hooks/settings.json").symlink_to(
            outside, target_is_directory=True
        )

        result = self._run(workspace)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("destination symlink", result.stderr)
        self.assertFalse((outside / "settings.json").exists())

    def test_rejects_non_file_direct_write_destinations_before_sync(self):
        destinations = (
            ".claude/hooks/settings.json",
            ".claude/.skills-sync-state",
            ".claude/.skills-sync-manifest",
            ".claude/settings.local.json.example",
            ".mcp.json.example",
        )
        for index, relative in enumerate(destinations):
            with self.subTest(destination=relative):
                workspace = self.root / f"non-file-destination-{index}"
                (workspace / relative).mkdir(parents=True)

                result = self._run(workspace)

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("destination must be a file", result.stderr)
                self.assertFalse((workspace / ".claude/rules/base.md").exists())

    def test_rejects_non_directory_write_roots_before_sync(self):
        for index, relative in enumerate((".claude", ".claude/hooks")):
            with self.subTest(destination=relative):
                workspace = self.root / f"non-directory-root-{index}"
                destination = workspace / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text("not a directory\n")

                result = self._run(workspace)

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("destination must be a directory", result.stderr)
                self.assertFalse((workspace / ".claude/rules/base.md").exists())

    def test_rejects_symlinked_sync_state_files_without_writing_outside(self):
        for filename in (".skills-sync-state", ".skills-sync-manifest"):
            with self.subTest(filename=filename):
                workspace = self.root / f"symlinked-{filename.removeprefix('.')}"
                outside = self.root / f"outside-{filename.removeprefix('.')}"
                (workspace / ".claude").mkdir(parents=True)
                outside.write_text("keep me\n")
                (workspace / ".claude" / filename).symlink_to(outside)

                result = self._run(workspace)

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("destination symlink", result.stderr)
                self.assertEqual(outside.read_text(), "keep me\n")

    def test_rejects_dangling_example_symlinks_without_writing_outside(self):
        destinations = (
            ".claude/settings.local.json.example",
            ".mcp.json.example",
        )
        for index, relative in enumerate(destinations):
            with self.subTest(destination=relative):
                workspace = self.root / f"symlinked-example-{index}"
                outside = self.root / f"outside-example-{index}"
                (workspace / ".claude").mkdir(parents=True)
                destination = workspace / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.symlink_to(outside)

                result = self._run(workspace)

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("destination symlink", result.stderr)
                self.assertFalse(outside.exists())

    # --- Hook installation tests ---

    def test_hooks_installed_to_dot_claude_hooks(self):
        """hooks/hooks/* must land in .claude/hooks/*, not .claude/hooks/hooks/*."""
        workspace = self.root / "hooks-install-workspace"
        workspace.mkdir()

        result = self._run(workspace)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(
            (workspace / ".claude/hooks/block-confidential.sh").is_file(),
            "hook script should be installed under .claude/hooks/",
        )
        self.assertFalse(
            (workspace / ".claude/hooks/hooks").exists(),
            "nested hooks/hooks dir must not appear under .claude/hooks/",
        )

    def test_hooks_settings_json_installed_as_reference_fragment(self):
        """hooks/settings.json must install as .claude/hooks/settings.json,
        never as .claude/settings.local.json."""
        workspace = self.root / "hooks-settings-workspace"
        workspace.mkdir()

        result = self._run(workspace)

        self.assertEqual(result.returncode, 0, result.stderr)
        fragment = workspace / ".claude/hooks/settings.json"
        self.assertTrue(fragment.is_file(), ".claude/hooks/settings.json should exist")
        self.assertEqual(fragment.read_text(), "hook-settings\n")
        self.assertFalse(
            (workspace / ".claude/settings.local.json").exists(),
            "settings.local.json must never be created by sync",
        )

    def test_rejects_colliding_hook_settings_sources(self):
        workspace = self.root / "colliding-hook-settings-workspace"
        workspace.mkdir()
        self.env["INJECT_COLLIDING_HOOK_SETTINGS"] = "1"

        result = self._run(workspace)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("hook source mapping collision", result.stderr)
        self.assertFalse((workspace / ".claude").exists())

    def test_dry_run_leaves_hooks_unwritten(self):
        """Dry-run must not create .claude/hooks."""
        workspace = self.root / "dry-run-hooks-workspace"
        workspace.mkdir()

        result = self._run(workspace, "--dry-run")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((workspace / ".claude/hooks").exists())

    def test_missing_hook_files_trigger_restore(self):
        """Missing installed hook files are detected and restored (like other tracked files)."""
        workspace = self.root / "restore-hooks-workspace"
        workspace.mkdir()

        first = self._run(workspace)
        self.assertEqual(first.returncode, 0, first.stderr)

        hook = workspace / ".claude/hooks/block-confidential.sh"
        self.assertTrue(hook.is_file())
        hook.unlink()

        restored = self._run(workspace)
        self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assertIn("missing locally", restored.stdout)
        self.assertTrue(hook.is_file())

    def test_hook_settings_fragment_participates_in_manifest(self):
        """hooks/settings.json installed as .claude/hooks/settings.json must appear in the manifest."""
        workspace = self.root / "hooks-manifest-workspace"
        workspace.mkdir()

        result = self._run(workspace)
        self.assertEqual(result.returncode, 0, result.stderr)

        manifest = workspace / ".claude/.skills-sync-manifest"
        self.assertTrue(manifest.is_file())
        entries = manifest.read_text()
        self.assertIn("hooks/settings.json", entries)

    def test_rejects_symlinks_in_hooks_payload(self):
        """Symlinks inside hooks/hooks/ must be rejected just like other symlinks."""
        workspace = self.root / "hooks-symlink-workspace"
        workspace.mkdir()
        self.env["INJECT_HOOK_SYMLINK"] = "1"

        result = self._run(workspace)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source symlink", result.stderr)

    def test_manifest_glob_metachar_does_not_expand_against_cwd(self):
        """Array-based manifest parsing must keep glob metacharacters literal.

        When INJECT_GLOB_MANIFEST is set, the fake tarball adds 'rules[1]' to
        shared-manifest.txt.  Because the manifest is parsed into a Bash array
        with a while-read loop (not via word-splitting of an unquoted variable),
        'rules[1]' is passed literally to the tarball lookup ($TMP/x/rules[1])
        which finds nothing and skips the item — the script still succeeds on
        the remaining valid items.  Without array parsing, 'rules[1]' would
        glob-expand against CWD and, if a matching directory existed there,
        silently install it as a sync source.
        """
        workspace = self.root / "glob-manifest-workspace"
        workspace.mkdir()
        # Create a CWD decoy that would match rules[1] if globbing were active.
        decoy = Path.cwd() / "rules1"
        decoy_created = False
        try:
            if not decoy.exists():
                decoy.mkdir()
                decoy_created = True
            self.env["INJECT_GLOB_MANIFEST"] = "1"

            result = self._run(workspace)

            # Script must succeed: valid manifest items (rules, agents …) still sync.
            self.assertEqual(result.returncode, 0, result.stderr)
            # The decoy directory must not have been treated as a sync source.
            self.assertFalse(
                (workspace / ".claude/rules1").exists(),
                "CWD 'rules1' must not be installed — glob expansion is suppressed by set -f",
            )
        finally:
            if decoy_created and decoy.exists():
                decoy.rmdir()

    def test_rejects_non_top_level_shared_manifest_entries(self):
        workspace = self.root / "nested-manifest-workspace"
        workspace.mkdir()
        self.env["INJECT_NESTED_MANIFEST"] = "1"

        result = self._run(workspace)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("top-level item", result.stderr)
        self.assertFalse((workspace / ".claude").exists())

    def test_rejects_option_like_shared_manifest_entries(self):
        workspace = self.root / "option-manifest-workspace"
        workspace.mkdir()
        self.env["INJECT_OPTION_MANIFEST"] = "1"

        result = self._run(workspace)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("top-level item", result.stderr)
        self.assertFalse((workspace / ".claude").exists())

    def test_rejects_valid_and_dangling_shared_manifest_symlinks(self):
        valid_target = self.root / "outside-shared-manifest.txt"
        valid_target.write_text("rules\n")
        targets = (valid_target, self.root / "missing-shared-manifest.txt")
        for index, target in enumerate(targets):
            with self.subTest(target=target):
                workspace = self.root / f"manifest-symlink-workspace-{index}"
                workspace.mkdir()
                self.env["INJECT_MANIFEST_SYMLINK"] = str(target)

                result = self._run(workspace)

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("source symlink", result.stderr)
                self.assertFalse((workspace / ".claude").exists())

    def test_rejects_shared_manifest_that_is_not_a_file(self):
        workspace = self.root / "manifest-directory-workspace"
        workspace.mkdir()
        self.env["INJECT_MANIFEST_DIRECTORY"] = "1"

        result = self._run(workspace)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("shared manifest must be a file", result.stderr)
        self.assertFalse((workspace / ".claude").exists())

    def test_rejects_empty_shared_manifest(self):
        workspace = self.root / "empty-manifest-workspace"
        workspace.mkdir()
        self.env["INJECT_EMPTY_MANIFEST"] = "1"

        result = self._run(workspace)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("shared manifest is empty", result.stderr)
        self.assertFalse((workspace / ".claude").exists())

    def test_reads_unterminated_final_shared_manifest_entry(self):
        workspace = self.root / "unterminated-manifest-workspace"
        workspace.mkdir()
        self.env["INJECT_UNTERMINATED_MANIFEST"] = "1"

        result = self._run(workspace)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((workspace / ".claude/rules/base.md").is_file())
        self.assertFalse((workspace / ".claude/agents").exists())
        self.assertFalse((workspace / ".claude/HOW-TO-USE.md").exists())

    def test_rejects_manifest_entries_for_personal_settings(self):
        workspace = self.root / "protected-manifest-workspace"
        personal = workspace / ".claude/settings.local.json"
        personal.parent.mkdir(parents=True)
        personal.write_text("personal settings\n")
        self.env["INJECT_PROTECTED_MANIFEST"] = "1"

        result = self._run(workspace)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("protected item", result.stderr)
        self.assertEqual(personal.read_text(), "personal settings\n")

    def test_manifest_protection_is_case_insensitive(self):
        protected_entries = ("SETTINGS.LOCAL.JSON", "SKILLS")
        for index, entry in enumerate(protected_entries):
            with self.subTest(entry=entry):
                workspace = self.root / f"cased-manifest-workspace-{index}"
                workspace.mkdir()
                self.env["INJECT_CASED_MANIFEST"] = entry

                result = self._run(workspace)

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("manifest", result.stderr)
                self.assertFalse((workspace / ".claude").exists())

    def test_rejects_remote_skills_root_that_is_not_a_directory(self):
        workspace = self.root / "invalid-remote-skills-workspace"
        private = workspace / ".claude/skills/_local/private.md"
        private.parent.mkdir(parents=True)
        private.write_text("private local skill\n")
        self.env["INJECT_SKILLS_FILE"] = "1"

        result = self._run(workspace)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("skills source must be a directory", result.stderr)
        self.assertEqual(private.read_text(), "private local skill\n")

    def test_rejects_remote_local_skill_directory_case_variants(self):
        for index, directory in enumerate(("_local", "_LOCAL", "_Local")):
            with self.subTest(directory=directory):
                workspace = self.root / f"remote-local-skill-{index}"
                private = workspace / ".claude/skills/_local/private.md"
                private.parent.mkdir(parents=True)
                private.write_text("personal local skill\n")
                self.env["INJECT_LOCAL_SKILL_CASE"] = directory

                result = self._run(workspace)

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("reserved local skill directory", result.stderr)
                self.assertEqual(private.read_text(), "personal local skill\n")

    def _run(self, workspace, *args):
        return subprocess.run(
            [str(SCRIPT), str(workspace), *args],
            capture_output=True,
            text=True,
            check=False,
            env=self.env,
        )

    def _run_with_gnu_type_conflict_guard(self, workspace, *args):
        real_rsync = shutil.which("rsync") or "/usr/bin/rsync"
        gnu_bin = self.root / "gnu-conflict-bin"
        gnu_bin.mkdir(exist_ok=True)
        wrapper = gnu_bin / "rsync"
        wrapper.write_text(
            '#!/usr/bin/env bash\n'
            'set -euo pipefail\n'
            'dry=0\n'
            'destination=""\n'
            'for argument in "$@"; do\n'
            '  [ "$argument" = "--dry-run" ] && dry=1\n'
            '  case "$argument" in --*) ;; *) destination="$argument" ;; esac\n'
            'done\n'
            'destination="${destination%/}"\n'
            'if [ "$dry" -eq 1 ] '
            '&& [ -d "$destination/rules/base.md" ]; then\n'
            '  echo "could not make way for new regular file" >&2\n'
            '  exit 23\n'
            'fi\n'
            f'exec "{real_rsync}" "$@"\n'
        )
        wrapper.chmod(0o755)
        environment = dict(self.env)
        environment["PATH"] = f"{gnu_bin}:{environment['PATH']}"
        return subprocess.run(
            [str(SCRIPT), str(workspace), *args],
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )

    def _install_mv_prompt_guard(self):
        real_mv = shutil.which("mv")
        self.assertIsNotNone(real_mv)
        self._write_executable(
            "mv",
            'force=0\n'
            'destination=""\n'
            'for argument in "$@"; do\n'
            '  [ "$argument" != "-f" ] || force=1\n'
            '  destination="$argument"\n'
            'done\n'
            'if [ "$force" -eq 0 ] && [ -e "$destination" ] '
            '&& [ ! -w "$destination" ]; then\n'
            '  exit 0\n'
            'fi\n'
            f'exec "{real_mv}" "$@"\n',
        )

    def _write_executable(self, name, body):
        path = self.bin / name
        path.write_text(f"#!/usr/bin/env bash\nset -euo pipefail\n{body}")
        path.chmod(0o755)


if __name__ == "__main__":
    unittest.main()
