from pathlib import Path
import os
import re

from sync_copilot_mapping import Mapping, is_markdown, split_frontmatter
from sync_copilot_yaml import load_yaml_mapping


def validate_before_render(
    claude: Path, github: Path, mappings: list[Mapping]
) -> list[str]:
    errors = validate_destination(github, github)
    for mapping in mappings:
        source_symlink = _first_symlink(claude, mapping.source)
        if source_symlink:
            errors.append(f"source symlink is not allowed: {source_symlink}")
        destination_errors = (
            validate_destination(
                github, mapping.destination,
                check_case=mapping.kind in {"skill", "resource"},
            )
            if mapping.generated else []
        )
        errors.extend(destination_errors)
        if not source_symlink and is_markdown(mapping.source):
            errors.extend(
                _validate_raw_frontmatter(mapping.source, skill=mapping.kind == "skill")
            )
        if (
            mapping.generated
            and not destination_errors
            and mapping.destination.is_file()
            and is_markdown(mapping.destination)
        ):
            errors.extend(_validate_raw_frontmatter(mapping.destination))
    return errors


def validate_rendered(
    mappings: list[Mapping],
    rendered: dict[Path, bytes],
) -> list[str]:
    planned = set(rendered)
    errors: list[str] = []
    for mapping in mappings:
        if not is_markdown(mapping.destination):
            continue
        text = rendered[mapping.destination].decode("utf-8")
        errors.extend(_validate_frontmatter(mapping.destination, text))
        if mapping.kind == "skill":
            errors.extend(_validate_skill_frontmatter(mapping.destination, text))
        errors.extend(_validate_links(mapping.destination, text, planned))
    return errors


def validate_destination(
    github: Path, destination: Path, *, check_case: bool = False
) -> list[str]:
    try:
        relative = destination.relative_to(github)
    except ValueError:
        return [f"destination escapes .github: {destination}"]
    symlink = _first_symlink(github, github / relative)
    if symlink:
        return [f"symlink destination is not allowed: {symlink}"]
    if github.exists() and not github.is_dir():
        return [f"destination root is not a directory: {github}"]
    current = github
    for part in relative.parts[:-1]:
        current /= part
        if current.exists() and not current.is_dir():
            return [f"destination parent is not a directory: {current}"]
    if relative.parts and destination.is_dir():
        return [f"destination must be a file: {destination}"]
    if check_case:
        mismatch = case_mismatch(github, destination)
        if mismatch:
            return [
                f"destination casing differs (case-only rename): {mismatch}; "
                "rename through a temporary name to match the source before syncing"
            ]
    return []


def case_mismatch(base: Path, path: Path) -> Path | None:
    current = base
    for part in path.relative_to(base).parts:
        child = current / part
        if not child.exists():
            return None
        if not any(entry.name == part for entry in current.iterdir()):
            return child
        current = child
    return None


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


def _validate_raw_frontmatter(path: Path, *, skill: bool = False) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [f"non-text source: {path}"]
    except OSError as error:
        return [f"cannot read {path}: {error}"]
    errors = _validate_frontmatter(path, text)
    if skill and not errors:
        errors.extend(_validate_skill_frontmatter(path, text))
    return errors


def _validate_frontmatter(path: Path, text: str) -> list[str]:
    if text.startswith("---\n") and "\n---\n" not in text[4:]:
        return [f"unclosed frontmatter: {path}"]
    return []


def _validate_skill_frontmatter(path: Path, text: str) -> list[str]:
    frontmatter, _ = split_frontmatter(text)
    if not frontmatter:
        return [f"skill requires YAML frontmatter with name and description: {path}"]
    try:
        metadata = load_yaml_mapping(frontmatter[4:-4], path)
    except ValueError as error:
        return [f"invalid skill frontmatter: {path}: {error}"]

    errors: list[str] = []
    name = metadata.get("name")
    if (
        not isinstance(name, str)
        or not 1 <= len(name) <= 64
        or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)
        or name != path.parent.name
    ):
        errors.append(
            f"invalid skill name: {path}: must match directory '{path.parent.name}' "
            "and use 1-64 lowercase letters, numbers, and single hyphens"
        )
    description = metadata.get("description")
    if (
        not isinstance(description, str)
        or not description.strip()
        or len(description) > 1024
    ):
        errors.append(f"skill description must be a non-empty string of at most 1024 characters: {path}")
    for field in ("disable-model-invocation", "user-invocable"):
        if field in metadata and not isinstance(metadata[field], bool):
            errors.append(f"skill {field} must be a boolean: {path}")
    if "argument-hint" in metadata and not isinstance(metadata["argument-hint"], str):
        errors.append(f"skill argument-hint must be a string: {path}")
    return errors


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
        if target.startswith(("./", "../", "references/", "scripts/", "assets/")):
            targets.append(target)
    for match in re.finditer(r"(?m)^\s*\[[^\]]+\]:\s*(<[^>]+>|\S+)", text):
        target = match.group(1).split("#", 1)[0].strip().strip("<>")
        if target.startswith(("./", "../", "references/", "scripts/", "assets/")):
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
