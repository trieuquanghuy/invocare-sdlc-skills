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


def is_markdown(path: Path) -> bool:
    return path.suffix.lower() in {".md", ".markdown"}


def split_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---\n"):
        return "", text
    end = text.find("\n---\n", 4)
    if end < 0:
        return "", text
    return text[: end + 5], text[end + 5 :]


def adapt_paths(text: str) -> str:
    replacements = (
        (r"\.claude/rules/([A-Za-z0-9_-]+)\.md", r".github/instructions/\1.instructions.md"),
        (r"\.claude/agents/([A-Za-z0-9_-]+)\.md", r".github/agents/\1.md"),
        # Per-machine runtime configuration must not become generated skill data.
        (r"\.claude/skills/(?!_shared/config(?=[/\s`\"')\]]|$))", ".github/skills/"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    return text


def render(mapping: Mapping) -> bytes:
    if not is_markdown(mapping.source):
        return mapping.source.read_bytes()
    try:
        source_text = mapping.source.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"non-text source: {mapping.source}") from error
    if mapping.kind not in {"rule", "agent"}:
        return adapt_paths(source_text).encode("utf-8")
    _, source_body = split_frontmatter(source_text)
    if mapping.destination.is_file() and not mapping.destination.is_symlink():
        frontmatter, _ = split_frontmatter(mapping.destination.read_text(encoding="utf-8"))
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
    return (frontmatter + "\n" + adapt_paths(source_body).lstrip("\n")).encode("utf-8")
