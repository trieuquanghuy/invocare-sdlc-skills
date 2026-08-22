#!/usr/bin/env python3
"""Policy tests for every skills/*/SKILL.md file.

Rules enforced:
1. Frontmatter block is present and properly closed (opened AND closed with `---`).
2. The `name:` field exactly matches the directory name.
3. Skills in WRITE_CAPABLE_ALLOWLIST must declare `disable-model-invocation: true`.
"""

import re
import unittest
from pathlib import Path

# ---------------------------------------------------------------------------
# Repository root resolution (works whether tests/ is cwd or not)
# ---------------------------------------------------------------------------
TESTS_DIR = Path(__file__).resolve().parent
SYNC_DIR = TESTS_DIR.parent
ROOT = SYNC_DIR.parents[1]
SKILLS_DIR = ROOT / "skills"

# Skills that perform writes and therefore must opt in to disable-model-invocation.
WRITE_CAPABLE_ALLOWLIST = {
    "apply-fix",
    "create-pr",
    "create-rca",
    "create-release-report",
    "create-spec",
    "pr-code-review-fixer",
    "prepare-uat",
    "publish-rca",
    "summarize-firebase-session",
    "ticket-comment",
}


# ---------------------------------------------------------------------------
# Frontmatter parser
# ---------------------------------------------------------------------------

def parse_frontmatter(text: str) -> dict[str, str] | None:
    """Return the YAML frontmatter key/value pairs from *text*, or None.

    Only reads up to the closing `---` on a line by itself.  A `---` that
    appears later in the Markdown body is ignored because we stop at the
    first closing delimiter.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None

    fm_lines: list[str] = []
    closed = False
    for line in lines[1:]:
        if line.strip() == "---":
            closed = True
            break
        fm_lines.append(line)

    if not closed:
        return None  # never found closing ---

    result: dict[str, str] = {}
    for line in fm_lines:
        # Simple key: value parsing (handles quoted and unquoted values)
        m = re.match(r'^(\S+?):\s*(.*)', line)
        if m:
            key = m.group(1)
            value = m.group(2).strip().strip('"').strip("'")
            result[key] = value
    return result


# ---------------------------------------------------------------------------
# Collect skill directories (exclude leading-underscore dirs)
# ---------------------------------------------------------------------------

def _skill_dirs() -> list[Path]:
    if not SKILLS_DIR.is_dir():
        return []
    return sorted(
        p for p in SKILLS_DIR.iterdir()
        if p.is_dir() and not p.name.startswith("_")
    )


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestSkillFrontmatter(unittest.TestCase):

    def _read(self, skill_dir: Path) -> tuple[str, dict[str, str]]:
        """Return (raw_text, parsed_frontmatter).  Fail fast if file missing."""
        skill_md = skill_dir / "SKILL.md"
        self.assertTrue(
            skill_md.exists(),
            f"[{skill_dir.name}] SKILL.md does not exist",
        )
        text = skill_md.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        self.assertIsNotNone(
            fm,
            f"[{skill_dir.name}] Frontmatter block is missing or not properly closed "
            f"(must start and end with a bare `---` line)",
        )
        return text, fm  # type: ignore[return-value]

    def test_all_skills_have_closed_frontmatter(self):
        """Every SKILL.md must open and close its frontmatter block."""
        failures: list[str] = []
        for skill_dir in _skill_dirs():
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                failures.append(f"[{skill_dir.name}] SKILL.md missing")
                continue
            text = skill_md.read_text(encoding="utf-8")
            fm = parse_frontmatter(text)
            if fm is None:
                failures.append(
                    f"[{skill_dir.name}] Frontmatter missing or unclosed"
                )
        if failures:
            self.fail("Frontmatter violations:\n  " + "\n  ".join(failures))

    def test_name_matches_directory(self):
        """The `name:` field must equal the directory name."""
        failures: list[str] = []
        for skill_dir in _skill_dirs():
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            text = skill_md.read_text(encoding="utf-8")
            fm = parse_frontmatter(text)
            if fm is None:
                continue  # caught by previous test
            name_val = fm.get("name", "")
            if name_val != skill_dir.name:
                failures.append(
                    f"[{skill_dir.name}] name: '{name_val}' != directory '{skill_dir.name}'"
                )
        if failures:
            self.fail("name: mismatches:\n  " + "\n  ".join(failures))

    def test_write_capable_skills_disable_model_invocation(self):
        """Write-capable skills must declare `disable-model-invocation: true`."""
        failures: list[str] = []
        for skill_dir in _skill_dirs():
            if skill_dir.name not in WRITE_CAPABLE_ALLOWLIST:
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                failures.append(f"[{skill_dir.name}] SKILL.md missing")
                continue
            text = skill_md.read_text(encoding="utf-8")
            fm = parse_frontmatter(text)
            if fm is None:
                failures.append(f"[{skill_dir.name}] Frontmatter unclosed; cannot check policy")
                continue
            dmi = fm.get("disable-model-invocation", "").lower()
            if dmi != "true":
                failures.append(
                    f"[{skill_dir.name}] disable-model-invocation: '{dmi or '(absent)'}' — must be 'true'"
                )
        if failures:
            self.fail(
                "Write-capable skills missing disable-model-invocation:\n  "
                + "\n  ".join(failures)
            )


if __name__ == "__main__":
    unittest.main()
