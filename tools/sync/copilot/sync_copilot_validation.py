from pathlib import Path
import os
import re

from sync_copilot_mapping import Mapping


def validate_before_render(
    claude: Path, github: Path, mappings: list[Mapping]
) -> list[str]:
    errors: list[str] = []
    for mapping in mappings:
        source_symlink = _first_symlink(claude, mapping.source)
        if source_symlink:
            errors.append(f"source symlink is not allowed: {source_symlink}")
        destination_errors = validate_destination(github, mapping.destination)
        errors.extend(destination_errors)
        if not source_symlink:
            errors.extend(_validate_raw_frontmatter(mapping.source))
        if not destination_errors and mapping.destination.is_file():
            errors.extend(_validate_raw_frontmatter(mapping.destination))
    return errors


def validate_rendered(
    mappings: list[Mapping],
    rendered: dict[Path, str],
) -> list[str]:
    planned = set(rendered)
    errors: list[str] = []
    for mapping in mappings:
        text = rendered[mapping.destination]
        errors.extend(_validate_frontmatter(mapping.destination, text))
        errors.extend(_validate_links(mapping.destination, text, planned))
    return errors


def validate_destination(github: Path, destination: Path) -> list[str]:
    try:
        relative = destination.relative_to(github)
    except ValueError:
        return [f"destination escapes .github: {destination}"]
    symlink = _first_symlink(github, github / relative)
    return [f"symlink destination is not allowed: {symlink}"] if symlink else []


def _first_symlink(base: Path, path: Path) -> Path | None:
    try:
        relative = path.relative_to(base)
    except ValueError:
        return path
    current = base
    if current.is_symlink():
        return current
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return current
    return None


def _validate_raw_frontmatter(path: Path) -> list[str]:
    try:
        text = path.read_text()
    except UnicodeDecodeError:
        return [f"non-text source: {path}"]
    except OSError as error:
        return [f"cannot read {path}: {error}"]
    return _validate_frontmatter(path, text)


def _validate_frontmatter(path: Path, text: str) -> list[str]:
    if text.startswith("---\n") and "\n---\n" not in text[4:]:
        return [f"unclosed frontmatter: {path}"]
    return []


def _validate_links(path: Path, text: str, planned: set[Path]) -> list[str]:
    errors: list[str] = []
    for target in _relative_link_targets(text):
        normalized = Path(os.path.abspath(path.parent / target))
        if normalized not in planned and not normalized.exists():
            errors.append(f"broken relative link: {path} -> {target}")
    return errors


def _relative_link_targets(text: str) -> list[str]:
    targets: list[str] = []
    for match in re.finditer(r"\]\(", text):
        target, _ = _read_balanced_destination(text, match.end())
        target = target.split("#", 1)[0].strip().strip("<>")
        if target.startswith(("./", "../")):
            targets.append(target)
    for match in re.finditer(r"(?m)^\s*\[[^\]]+\]:\s*(<[^>]+>|\S+)", text):
        target = match.group(1).split("#", 1)[0].strip().strip("<>")
        if target.startswith(("./", "../")):
            targets.append(target)
    return targets


def _read_balanced_destination(text: str, start: int) -> tuple[str, int]:
    depth = 0
    escaped = False
    characters: list[str] = []
    for index in range(start, len(text)):
        character = text[index]
        if escaped:
            characters.append(character)
            escaped = False
        elif character == "\\":
            characters.append(character)
            escaped = True
        elif character == "(":
            depth += 1
            characters.append(character)
        elif character == ")":
            if depth == 0:
                return "".join(characters), index
            depth -= 1
            characters.append(character)
        else:
            characters.append(character)
    return "".join(characters), len(text)
