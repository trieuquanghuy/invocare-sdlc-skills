"""Map Claude source files into generated Copilot files."""

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class Mapping:
    source: Path
    destination: Path
    kind: str
    skill: str | None = None


def split_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---\n"):
        return "", text
    end = text.find("\n---\n", 4)
    if end < 0:
        return "", text
    return text[: end + 5], text[end + 5 :]


def adapt_paths(text: str, skill: str | None = None) -> str:
    replacements = (
        (r"\.claude/rules/([A-Za-z0-9_-]+)\.md", r".github/instructions/\1.instructions.md"),
        (r"\.claude/agents/([A-Za-z0-9_-]+)\.md", r".github/agents/\1.md"),
        (
            r"\.claude/skills/_shared/templates/([^` )]+)",
            r".github/prompts/references/_shared/\1",
        ),
        (
            r"\.claude/skills/_shared/contracts/([^` )]+)",
            r".github/prompts/references/_shared/\1",
        ),
        (
            r"\.claude/skills/_shared/references/([^` )]+)",
            r".github/prompts/_shared/references/\1",
        ),
        (
            r"\.claude/skills/([A-Za-z0-9_-]+)/references/([^` )]+)",
            r".github/prompts/references/\1/\2",
        ),
        (
            r"\.claude/skills/([A-Za-z0-9_-]+)/code-checker-prompt\.md",
            r".github/prompts/\1-code-checker.prompt.md",
        ),
        (
            r"\.claude/skills/([A-Za-z0-9_-]+)/checker-prompt\.md",
            r".github/prompts/\1-checker.prompt.md",
        ),
        (
            r"\.claude/skills/([A-Za-z0-9_-]+)/SKILL\.md",
            r".github/prompts/\1.prompt.md",
        ),
    )
    text = text.replace(".claude/skills/**", ".github/prompts/**")
    text = text.replace(
        ".claude/skills/*/checker-prompt.md",
        ".github/prompts/*-checker.prompt.md",
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    if skill:
        text = text.replace(
            "../create-validation/references/",
            "./references/create-validation/",
        )
        text = text.replace(
            "../_shared/templates/",
            "./references/_shared/",
        )
        text = text.replace(
            "./code-checker-prompt.md",
            f"./{skill}-code-checker.prompt.md",
        )
        text = text.replace(
            "./checker-prompt.md",
            f"./{skill}-checker.prompt.md",
        )
        text = text.replace("./references/", f"./references/{skill}/")
        text = text.replace(
            f"./references/{skill}/create-validation/",
            "./references/create-validation/",
        )
        text = text.replace(
            f"./references/{skill}/_shared/",
            "./references/_shared/",
        )
        text = re.sub(
            r"(?<![/A-Za-z0-9_.-])references/",
            f"./references/{skill}/",
            text,
        )
    return text


def render(mapping: Mapping) -> str:
    try:
        source_text = mapping.source.read_text()
    except UnicodeDecodeError as error:
        raise ValueError(f"non-text source: {mapping.source}") from error
    if mapping.kind not in {"rule", "agent"}:
        return adapt_paths(source_text, mapping.skill)
    _, source_body = split_frontmatter(source_text)
    if mapping.destination.is_file() and not mapping.destination.is_symlink():
        frontmatter, _ = split_frontmatter(mapping.destination.read_text())
    else:
        frontmatter = ""
    if not frontmatter and mapping.kind == "rule":
        frontmatter = (
            '---\napplyTo: "**"\n'
            f'description: "{mapping.source.stem} governance rules."\n---\n'
        )
    if not frontmatter:
        source_frontmatter, _ = split_frontmatter(source_text)
        match = re.search(r"^description:\s*(.+)$", source_frontmatter, re.MULTILINE)
        description = match.group(1) if match else f"'{mapping.source.stem} agent'"
        frontmatter = (
            f"---\ndescription: {description}\n"
            "tools: ['codebase', 'search', 'fetch']\n---\n"
        )
    return frontmatter + "\n" + adapt_paths(source_body).lstrip("\n")
