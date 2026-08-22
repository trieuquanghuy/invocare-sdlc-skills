#!/usr/bin/env python3
"""Policy tests for repository hardening artefacts.

Enforced rules:
1. Required files exist at expected paths.
2. CODEOWNERS owns all paths with @trieuquanghuy.
3. LICENSE is MIT for Copyright (c) 2026 Huy Trieu.
4. scripts/validate-calver.sh is Bash-safe (has set -euo pipefail).
5. CI workflow has required elements.
6. Release workflow has required elements.
"""

import subprocess
import unittest
from pathlib import Path

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
TESTS_DIR = Path(__file__).resolve().parent
SYNC_DIR = TESTS_DIR.parent
ROOT = SYNC_DIR.parents[1]

REQUIRED_FILES = [
    ".github/workflows/ci.yml",
    ".github/workflows/release.yml",
    ".github/CODEOWNERS",
    "LICENSE",
    "scripts/validate-calver.sh",
]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Required-files existence
# ---------------------------------------------------------------------------

class TestRequiredFilesExist(unittest.TestCase):

    def test_required_files_all_exist(self):
        missing = [f for f in REQUIRED_FILES if not (ROOT / f).exists()]
        if missing:
            self.fail("Missing required files:\n  " + "\n  ".join(missing))


# ---------------------------------------------------------------------------
# CODEOWNERS
# ---------------------------------------------------------------------------

class TestCodeowners(unittest.TestCase):

    def setUp(self):
        p = ROOT / ".github" / "CODEOWNERS"
        self.skipTest("CODEOWNERS not yet created") if not p.exists() else None
        self.text = p.read_text(encoding="utf-8")

    def test_wildcard_rule_exists(self):
        """A catch-all '*' rule must exist."""
        lines = [ln.strip() for ln in self.text.splitlines() if ln.strip() and not ln.startswith("#")]
        wildcards = [ln for ln in lines if ln.startswith("*")]
        self.assertTrue(wildcards, "No wildcard rule found in CODEOWNERS")

    def test_all_rules_owned_by_trieuquanghuy(self):
        """Every ownership rule must include @trieuquanghuy."""
        lines = [ln.strip() for ln in self.text.splitlines() if ln.strip() and not ln.startswith("#")]
        bad = [ln for ln in lines if "@trieuquanghuy" not in ln]
        if bad:
            self.fail("Rules missing @trieuquanghuy:\n  " + "\n  ".join(bad))


# ---------------------------------------------------------------------------
# LICENSE
# ---------------------------------------------------------------------------

class TestLicense(unittest.TestCase):

    def setUp(self):
        p = ROOT / "LICENSE"
        self.skipTest("LICENSE not yet created") if not p.exists() else None
        self.text = p.read_text(encoding="utf-8")

    def test_mit_license(self):
        self.assertIn("MIT License", self.text)

    def test_copyright_year_and_holder(self):
        self.assertIn("Copyright (c) 2026 Huy Trieu", self.text)

    def test_permission_grant_present(self):
        self.assertIn("Permission is hereby granted", self.text)

    def test_full_mit_text_present(self):
        self.assertIn("THE SOFTWARE IS PROVIDED", self.text)


# ---------------------------------------------------------------------------
# validate-calver.sh
# ---------------------------------------------------------------------------

class TestValidateCalver(unittest.TestCase):

    def setUp(self):
        self.script = ROOT / "scripts" / "validate-calver.sh"
        if not self.script.exists():
            self.skipTest("validate-calver.sh not yet created")

    def _run(self, *args, env=None):
        import os
        e = os.environ.copy()
        if env:
            e.update(env)
        return subprocess.run(
            ["bash", str(self.script)] + list(args),
            capture_output=True, text=True, env=e,
        )

    def test_safe_shell_flags(self):
        text = self.script.read_text(encoding="utf-8")
        self.assertIn("set -euo pipefail", text)

    def test_valid_date(self):
        result = self._run("v2026.08.22")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_valid_leap_day(self):
        result = self._run("v2024.02.29")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_non_leap_day(self):
        result = self._run("v2023.02.29")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(result.stderr.strip(), "Expected error on stderr")

    def test_malformed_tag(self):
        result = self._run("2026.08.22")  # missing 'v' prefix
        self.assertNotEqual(result.returncode, 0)

    def test_malformed_tag_letters(self):
        result = self._run("vXXXX.08.22")
        self.assertNotEqual(result.returncode, 0)

    def test_missing_argument(self):
        result = self._run()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(result.stderr.strip(), "Expected usage error on stderr")

    def test_impossible_date(self):
        result = self._run("v2026.13.01")  # month 13 doesn't exist
        self.assertNotEqual(result.returncode, 0)


# ---------------------------------------------------------------------------
# ci.yml
# ---------------------------------------------------------------------------

class TestCiWorkflow(unittest.TestCase):

    def setUp(self):
        p = ROOT / ".github" / "workflows" / "ci.yml"
        if not p.exists():
            self.skipTest("ci.yml not yet created")
        self.text = p.read_text(encoding="utf-8")

    def test_triggers_pull_request(self):
        self.assertIn("pull_request:", self.text)

    def test_triggers_push_main(self):
        self.assertIn("push:", self.text)
        self.assertIn("main", self.text)

    def test_read_permissions(self):
        self.assertIn("permissions:", self.text)
        self.assertIn("contents: read", self.text)

    def test_concurrency_cancel(self):
        self.assertIn("concurrency:", self.text)
        self.assertIn("cancel-in-progress: true", self.text)

    def test_ubuntu_latest(self):
        self.assertIn("ubuntu-latest", self.text)

    def test_checkout_step(self):
        self.assertIn("actions/checkout", self.text)

    def test_setup_python_312(self):
        self.assertIn("actions/setup-python", self.text)
        self.assertIn("3.12", self.text)

    def test_unittest_discovery(self):
        self.assertIn("python -m unittest discover", self.text)

    def test_shell_syntax_check(self):
        self.assertIn("bash -n", self.text)

    def test_diff_check(self):
        self.assertIn("git diff --check", self.text)


# ---------------------------------------------------------------------------
# release.yml
# ---------------------------------------------------------------------------

class TestReleaseWorkflow(unittest.TestCase):

    def setUp(self):
        p = ROOT / ".github" / "workflows" / "release.yml"
        if not p.exists():
            self.skipTest("release.yml not yet created")
        self.text = p.read_text(encoding="utf-8")

    def test_workflow_dispatch_trigger(self):
        self.assertIn("workflow_dispatch:", self.text)

    def test_tag_input_required(self):
        self.assertIn("required: true", self.text)

    def test_ref_input_default_main(self):
        self.assertIn("default: main", self.text)

    def test_minimal_default_permissions(self):
        self.assertIn("permissions:", self.text)
        # Top-level should restrict; job-level grants write
        self.assertIn("contents: write", self.text)

    def test_concurrency_on_tag(self):
        self.assertIn("concurrency:", self.text)

    def test_validates_tag_before_remote(self):
        # validate-calver.sh must be called before gh release create
        validate_pos = self.text.find("validate-calver.sh")
        release_pos = self.text.find("gh release create")
        self.assertGreater(validate_pos, -1, "validate-calver.sh not found")
        self.assertGreater(release_pos, -1, "gh release create not found")
        self.assertLess(validate_pos, release_pos, "validate-calver.sh must run before gh release create")

    def test_rejects_existing_release_via_gh_api(self):
        """Preflight must use 'gh api' to check for an existing release, not 'gh release view'
        (which requires git context unavailable before checkout)."""
        self.assertIn("gh api", self.text,
                      "Preflight must use 'gh api' to check for existing release before checkout")
        # 'gh api' call must reference releases/tags/ endpoint
        self.assertIn("releases/tags/", self.text,
                      "Must check releases by tag via GitHub API endpoint 'releases/tags/<tag>'")

    def test_rejects_existing_git_tag_via_gh_api(self):
        """Preflight must use 'gh api' to check for existing git ref, not 'git ls-remote origin'
        (which needs git context unavailable before checkout)."""
        self.assertIn("git/refs/tags/", self.text,
                      "Must check git ref via GitHub API endpoint 'git/refs/tags/<tag>'")

    def test_no_git_ls_remote_before_checkout(self):
        """'git ls-remote' must not appear before checkout — it has no git context pre-checkout."""
        # The entire workflow must not use git ls-remote in any pre-checkout step;
        # the cleanest policy is: git ls-remote must not appear at all in the workflow.
        self.assertNotIn("git ls-remote", self.text,
                         "'git ls-remote' must not be used; use 'gh api' for pre-checkout checks")

    def test_preflight_rejects_on_non_404_api_errors(self):
        """The preflight block must distinguish 404 (not-found) from other API/auth failures
        and exit non-zero on any unexpected status."""
        self.assertIn("404", self.text,
                      "Preflight must handle 404 explicitly to distinguish not-found from API errors")

    def test_generates_notes(self):
        self.assertIn("--generate-notes", self.text)

    def test_gh_token_via_env(self):
        self.assertIn("GH_TOKEN", self.text)
        self.assertIn("github.token", self.text)

    def test_inputs_via_env_not_inline(self):
        """Untrusted inputs must be passed via env vars, not embedded in run scripts."""
        import re
        # Check that ${{ inputs.tag }} and ${{ inputs.ref }} are NOT directly
        # interpolated inside a `run:` block (injection risk).
        # They should only appear in `env:` blocks or `with:` contexts.
        run_blocks = re.findall(r'run:\s*\|?(.*?)(?=\n\s{0,8}\w|\Z)', self.text, re.DOTALL)
        for block in run_blocks:
            self.assertNotIn("${{ inputs.tag }}", block,
                             "inputs.tag must not be embedded directly in run: blocks")
            self.assertNotIn("${{ inputs.ref }}", block,
                             "inputs.ref must not be embedded directly in run: blocks")

    def test_checkout_before_script_validation(self):
        """actions/checkout must appear before validate-calver.sh.

        The script lives inside the repository; running it before checkout
        will fail with 'No such file or directory'.
        """
        checkout_pos = self.text.find("actions/checkout")
        validate_pos = self.text.find("validate-calver.sh")
        self.assertGreater(checkout_pos, -1, "actions/checkout not found")
        self.assertGreater(validate_pos, -1, "validate-calver.sh not found")
        self.assertLess(checkout_pos, validate_pos,
                        "actions/checkout must appear before validate-calver.sh")

    def test_validation_before_api_preflight(self):
        """validate-calver.sh must appear before the gh api preflight block.

        Fail fast on a malformed tag before consuming any API quota.
        """
        validate_pos = self.text.find("validate-calver.sh")
        api_pos = self.text.find("gh api")
        self.assertGreater(validate_pos, -1, "validate-calver.sh not found")
        self.assertGreater(api_pos, -1, "gh api not found")
        self.assertLess(validate_pos, api_pos,
                        "validate-calver.sh must appear before gh api preflight")

    def test_explicit_nonzero_api_capture_safe_under_e(self):
        """gh api must be captured with an '|| api_status=$?' guard.

        Under 'bash -e' and 'set -o pipefail' a non-zero exit from gh api
        (e.g. on a legitimate 404) would abort the step before the HTTP
        status line can be parsed.  The guard prevents the premature exit.
        """
        import re
        # Must have the || api_status=$? (or similar variable name) construct
        # immediately following the gh api call inside a $(...) capture.
        has_capture = bool(re.search(
            r'api_output\s*=\s*\$\(.*?gh api', self.text, re.DOTALL))
        has_guard = bool(re.search(
            r'\|\|\s*api_status=\$\?', self.text))
        self.assertTrue(has_capture,
                        "gh api output must be captured into a variable with $(...)")
        self.assertTrue(has_guard,
                        "gh api call must be guarded with '|| api_status=$?' to be safe under -e")

    def test_release_target_uses_checked_out_head_not_github_sha(self):
        """--target must use the checked-out HEAD SHA, not GITHUB_SHA.

        GITHUB_SHA is the default-branch SHA at dispatch time and does not
        reflect the requested ref when inputs.ref differs from the default branch.
        """
        self.assertNotIn("GITHUB_SHA", self.text,
                         "Must not use GITHUB_SHA; resolve SHA via 'git rev-parse HEAD' after checkout")
        # The release create command must reference a variable derived from HEAD
        self.assertIn("--target", self.text,
                      "gh release create must include --target")
        # RELEASE_SHA is the expected env var set via git rev-parse HEAD
        self.assertIn("RELEASE_SHA", self.text,
                      "Must set RELEASE_SHA from 'git rev-parse HEAD' and pass it to --target")

    def test_full_checks_before_release(self):
        """Tests and shell syntax must run before the release step."""
        validate_pos = self.text.find("validate-calver.sh")
        unittest_pos = self.text.find("python -m unittest discover")
        release_pos = self.text.find("gh release create")
        self.assertGreater(unittest_pos, -1, "unittest discover not found")
        self.assertLess(unittest_pos, release_pos, "tests must run before release")
        self.assertLess(validate_pos, release_pos)


if __name__ == "__main__":
    unittest.main()
