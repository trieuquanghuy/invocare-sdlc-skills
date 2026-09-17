#!/usr/bin/env python3

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "copilot/generate.py"


class CopilotCompatibilityTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name).resolve()
        self.source = self.workspace / ".claude"
        self.target = self.workspace / ".github"
        self._write(
            ".claude/agents/reviewer.md",
            "---\nname: reviewer\ndescription: Shared review role\n"
            "tools: [Read, Bash]\nmodel: sonnet\n---\n# Review\n",
        )
        self._write(
            ".claude/copilot/agents/reviewer.yaml",
            "description: Copilot review role\nmodel: null\n"
            "tools: [view, bash, create, repo-search/search]\n",
        )
        self._write(
            ".claude/rules/base.md",
            "---\npaths: src/**\n---\n"
            "Enforcement requires `.claude/scripts/sdlc-gate.sh`.\n",
        )
        self.skill = self._write(
            ".claude/skills/base/SKILL.md",
            "---\nname: base\ndescription: Shared skill\n"
            'argument-hint: "[file]"\ndisable-model-invocation: true\n---\n'
            "Use `mcp__lesson-runtime__lesson_learned`.\n",
        )

    def _write(self, relative, content):
        path = self.workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(self.workspace), *args],
            capture_output=True, text=True, check=False,
        )

    def _snapshot(self):
        return {
            path.relative_to(self.workspace).as_posix(): path.read_bytes()
            for path in self.workspace.rglob("*")
            if path.is_file()
        }

    def test_report_is_structured_read_only_and_distinguishes_runtime(self):
        before = self._snapshot()
        result = self._run("--compatibility-report")

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["client"], "copilot-cli")
        self.assertEqual(report["baseline_version"], "1.0.83")
        self.assertTrue(report["read_only"])
        self.assertEqual(report["static_status"], "valid")
        self.assertEqual(report["runtime_verification"], "not_performed")
        self.assertEqual(report["skills_mode"], "mirror")
        self.assertEqual(report["errors"], [])
        self.assertEqual(
            report["counts"], {"agents": 1, "rules": 1, "skills": 1, "resources": 0}
        )
        self.assertEqual(self._snapshot(), before)
        self.assertFalse(self.target.exists())

    def test_report_exposes_selected_profile_model_and_invocation_policy(self):
        result = self._run("--compatibility-report")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)

        agent = report["agents"][0]
        self.assertEqual(agent["profile"], "copilot/agents/reviewer.yaml")
        self.assertEqual(agent["model"], {"policy": "session", "id": None})
        self.assertEqual(agent["tools"], ["view", "bash", "create", "repo-search/search"])
        skill = report["skills"][0]
        self.assertTrue(skill["user_invocable"])
        self.assertFalse(skill["model_invocable"])
        self.assertEqual(skill["argument_hint"], "[file]")
        self.assertEqual(skill["location"], str(self.target / "skills/base/SKILL.md"))
        self.assertEqual(report["rules"][0]["applyTo"], "src/**")

    def test_report_does_not_inspect_credentials_or_claim_mcp_is_missing(self):
        config = self._write(
            ".mcp.json",
            '{"mcpServers":{"private-server":{"token":"DO_NOT_DISCLOSE"}}}\n',
        )
        config.chmod(0)
        try:
            result = self._run("--compatibility-report")
        finally:
            config.chmod(0o600)

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["mcp"]["configuration"], "not_inspected")
        self.assertEqual(report["mcp"]["availability"], "not_verified")
        self.assertEqual(report["mcp"]["required_tools"], ["repo-search/search"])
        self.assertIn(
            "mcp__lesson-runtime__lesson_learned",
            report["mcp"]["shared_claude_references"],
        )
        self.assertNotIn("DO_NOT_DISCLOSE", result.stdout + result.stderr)
        self.assertNotIn("private-server", result.stdout + result.stderr)
        self.assertIn("personal", report["mcp"]["guidance"])
        self.assertIn("plugin", report["mcp"]["guidance"])

    def test_report_distinguishes_hooks_and_scripts_from_enforcement(self):
        self._write(".claude/settings.json", '{"hooks":{"not-parsed":"SENSITIVE"}}\n')
        result = self._run("--compatibility-report")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)

        self.assertEqual(report["hooks"]["configuration"], "not_converted")
        self.assertEqual(report["hooks"]["enforcement"], "not_verified")
        self.assertIn(
            {"path": ".claude/scripts/sdlc-gate.sh", "present": False},
            report["hooks"]["referenced_scripts"],
        )
        self.assertNotIn("SENSITIVE", result.stdout + result.stderr)
        self.assertIn(
            "HOOK_RUNTIME_UNVERIFIED",
            {warning["code"] for warning in report["warnings"]},
        )

    def test_native_report_uses_native_paths_and_warns_about_added_roots(self):
        result = self._run("--compatibility-report", "--skills-mode", "native")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)

        self.assertEqual(report["skills_mode"], "native")
        self.assertEqual(report["skills"][0]["location"], str(self.skill))
        self.assertIn("added-root", report["discovery"]["guidance"])
        self.assertIn(".github", report["discovery"]["guidance"])
        self.assertFalse(self.target.exists())

    def test_report_exposes_agent_invocation_controls_and_target_mismatches(self):
        self._write(
            ".claude/copilot/agents/reviewer.yaml",
            "model: null\ntools: [view]\ntarget: github-copilot\n"
            "user-invocable: false\ndisable-model-invocation: true\n",
        )
        result = self._run("--compatibility-report")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        agent = report["agents"][0]
        self.assertEqual(agent["target"], "github-copilot")
        self.assertEqual(
            agent["invocation"],
            {"user-invocable": False, "disable-model-invocation": True},
        )
        self.assertIn(
            "AGENT_TARGET_MISMATCH",
            {warning["code"] for warning in report["warnings"]},
        )

    def test_report_preserves_an_existing_generated_tree(self):
        applied = self._run()
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self._write(".github/local-note.md", "# Local\n")
        before = self._snapshot()
        result = self._run("--compatibility-report")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self._snapshot(), before)
        self.assertEqual(json.loads(result.stdout)["sync_preview"]["created"], 0)

    def test_report_flags_untranslated_skill_execution_extensions(self):
        self.skill.write_text(
            "---\nname: base\ndescription: Shared\ncontext: fork\nagent: Explore\n"
            "allowed-tools: Read\n---\n# Base\n"
        )
        result = self._run("--compatibility-report")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)

        self.assertIn(
            "SKILL_EXECUTION_EXTENSIONS",
            {warning["code"] for warning in report["warnings"]},
        )
        self.assertIn("context", report["skills"][0]["extensions"])
        self.assertIn("agent", report["skills"][0]["extensions"])
        self.assertIn(
            "SKILL_TOOL_PREAPPROVAL",
            {warning["code"] for warning in report["warnings"]},
        )

    def test_invalid_profiles_produce_a_blocked_json_report_without_writes(self):
        self._write(
            ".claude/copilot/agents/reviewer.yaml",
            "model: null\ntools: [view]\ntools: [bash]\n",
        )
        before = self._snapshot()
        result = self._run("--compatibility-report")

        self.assertNotEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertEqual(report["static_status"], "blocked")
        self.assertIn("duplicate", "\n".join(report["errors"]))
        self.assertEqual(report["runtime_verification"], "not_performed")
        self.assertEqual(self._snapshot(), before)
        self.assertFalse(self.target.exists())

    def test_report_cannot_be_combined_with_mutating_prune(self):
        result = self._run("--compatibility-report", "--prune")
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot be combined", result.stderr)
        self.assertFalse(self.target.exists())

    def test_non_string_argument_hint_is_rejected_before_rendering(self):
        self.skill.write_text(
            "---\nname: base\ndescription: Shared\nargument-hint: 2026-01-01\n"
            "---\n# Base\n"
        )
        result = self._run()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("argument-hint must be a string", result.stderr)
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
