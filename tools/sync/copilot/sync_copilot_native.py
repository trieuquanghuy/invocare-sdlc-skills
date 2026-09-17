from dataclasses import dataclass
from pathlib import Path

from sync_copilot_discovery import visible_files
from sync_copilot_validation import validate_destination
from sync_copilot_yaml import load_yaml_mapping, split_frontmatter


@dataclass(frozen=True)
class SkillShadow:
    name: str
    path: Path


def validate_native_layout(source: Path, github: Path) -> None:
    if (
        source.name != ".claude"
        or github.name != ".github"
        or source.parent != github.parent
    ):
        raise ValueError(
            "native skills require persistent, adjacent workspace/.claude and "
            "workspace/.github directories; use mirror mode for external sources"
        )


def find_skill_shadows(
    source: Path, github: Path, names: set[str]
) -> list[SkillShadow]:
    shadows: list[SkillShadow] = []
    for root in (github / "skills", source.parent / ".agents/skills"):
        errors = validate_destination(root.parent, root.parent)
        if root.is_symlink():
            errors.append(f"symlink discovery root is not allowed: {root}")
        if errors:
            raise ValueError("\n".join(errors))
        if not root.exists():
            continue
        if not root.is_dir():
            raise ValueError(f"skill discovery root is not a directory: {root}")
        for path in visible_files(root, excluded=None):
            if path.name != "SKILL.md":
                continue
            frontmatter, _ = split_frontmatter(path.read_text(encoding="utf-8"))
            if not frontmatter:
                raise ValueError(f"cannot determine skill shadows without frontmatter: {path}")
            metadata = load_yaml_mapping(frontmatter[4:-4], path)
            name = metadata.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"cannot determine skill shadows without a valid name: {path}")
            if name in names:
                shadows.append(SkillShadow(name, path))
    return shadows


def validate_native_shadows(
    source: Path, github: Path, names: set[str],
    owned: frozenset[str], *, prune: bool,
) -> list[str]:
    errors: list[str] = []
    for shadow in find_skill_shadows(source, github, names):
        managed = (
            shadow.path.is_relative_to(github)
            and shadow.path.relative_to(github).as_posix() in owned
        )
        if managed and prune:
            continue
        resolution = (
            "rerun with --prune to retire the owned mirror"
            if managed else
            "reconcile or move the unmanaged shadow; it will not be deleted"
        )
        errors.append(
            f"higher-priority skill shadows native '{shadow.name}': "
            f"{shadow.path}; {resolution}"
        )
    return errors
