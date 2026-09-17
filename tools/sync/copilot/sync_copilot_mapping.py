"""Map Claude source files into generated Copilot files."""

from dataclasses import dataclass
from pathlib import Path
import re

import yaml

from sync_copilot_metadata import agent_metadata, rule_metadata
from sync_copilot_yaml import split_frontmatter


@dataclass(frozen=True)
class Mapping:
    source: Path
    destination: Path
    kind: str
    skill: str | None = None
    generated: bool = True


def is_markdown(path: Path) -> bool:
    return path.suffix.lower() in {".md", ".markdown"}


def adapt_paths(
    text: str, *, skills_mode: str = "mirror",
    path_mappings: dict[str, str] | None = None,
) -> str:
    for original, destination in sorted(
        (path_mappings or {}).items(), key=lambda pair: len(pair[0]), reverse=True
    ):
        text = text.replace(original, destination)
    replacements = (
        (
            r"\.claude/rules/((?:[A-Za-z0-9_-][A-Za-z0-9_.-]*/)*[A-Za-z0-9_-][A-Za-z0-9_.-]*)\.md",
            r".github/instructions/\1.instructions.md",
        ),
        (r"\.claude/agents/([A-Za-z0-9_-]+)\.md", r".github/agents/\1.md"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    if skills_mode == "mirror":
        # Per-machine runtime configuration must not become generated skill data.
        text = re.sub(
            r"\.claude/skills/(?!_shared/config(?=[/\s`\"')\]]|$))",
            ".github/skills/",
            text,
        )
    return text


def render(
    mapping: Mapping, source_root: Path, *, skills_mode: str = "mirror",
    path_mappings: dict[str, str] | None = None,
) -> bytes:
    if not mapping.generated or not is_markdown(mapping.source):
        return mapping.source.read_bytes()
    try:
        source_text = mapping.source.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"non-text source: {mapping.source}") from error
    if mapping.kind not in {"rule", "agent"}:
        return adapt_paths(
            source_text, skills_mode=skills_mode, path_mappings=path_mappings
        ).encode("utf-8")
    _, source_body = split_frontmatter(source_text)
    metadata = (
        rule_metadata(mapping.source, source_text)
        if mapping.kind == "rule"
        else agent_metadata(source_root, mapping.source, source_text)
    )
    frontmatter = "---\n" + yaml.safe_dump(metadata, sort_keys=False) + "---\n"
    body = adapt_paths(
        source_body, skills_mode=skills_mode, path_mappings=path_mappings
    ).lstrip("\n")
    return (frontmatter + "\n" + body).encode("utf-8")
