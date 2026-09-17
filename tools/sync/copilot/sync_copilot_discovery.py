from collections.abc import Iterator
from pathlib import Path

from sync_copilot_mapping import Mapping


def discover(
    claude: Path, github: Path, *, skills_mode: str = "mirror"
) -> list[Mapping]:
    mappings: list[Mapping] = []
    rules = claude / "rules"
    for source in visible_files(rules, excluded=None):
        if source.suffix != ".md":
            continue
        mappings.append(
            Mapping(
                source,
                github / "instructions" / source.relative_to(rules).with_suffix(".instructions.md"),
                "rule",
            )
        )
    for source in sorted((claude / "agents").glob("*.md")):
        mappings.append(Mapping(source, github / "agents" / source.name, "agent"))
    skills = claude / "skills"
    generated = skills_mode == "mirror"
    destination = github / "skills" if generated else skills
    for directory in sorted(skills.iterdir()):
        if directory.name.startswith(".") or directory.name == "_local":
            continue
        if directory.is_symlink():
            raise ValueError(f"source symlink is not allowed: {directory}")
        if not directory.is_dir():
            continue
        if directory.name == "_shared":
            _add_tree(mappings, directory, destination / "_shared", generated=generated)
        else:
            _add_skill_mappings(
                mappings, destination, directory, directory.name, generated=generated
            )
    destinations = [mapping.destination for mapping in mappings]
    if len(destinations) != len(set(destinations)):
        raise ValueError("source mappings contain destination collisions")
    return mappings


def _add_skill_mappings(
    mappings: list[Mapping], destination: Path, directory: Path, skill: str,
    *, generated: bool,
) -> None:
    main = directory / "SKILL.md"
    if main.is_symlink():
        raise ValueError(f"source symlink is not allowed: {main}")
    if not main.is_file() or "SKILL.md" not in {path.name for path in directory.iterdir()}:
        raise ValueError(f"skill requires an exactly named SKILL.md: {directory}")
    _add_tree(mappings, directory, destination / skill, skill, generated=generated)


def _add_tree(
    mappings: list[Mapping],
    source_dir: Path,
    destination: Path,
    skill: str | None = None,
    *,
    generated: bool = True,
) -> None:
    if not source_dir.is_dir():
        return
    runtime_config = source_dir / "config" if skill is None else None
    for source in visible_files(source_dir, excluded=runtime_config):
        relative = source.relative_to(source_dir)
        mappings.append(
            Mapping(
                source,
                destination / relative,
                "skill" if skill and relative == Path("SKILL.md") else "resource",
                skill,
                generated,
            )
        )


def visible_files(directory: Path, *, excluded: Path | None) -> Iterator[Path]:
    for source in sorted(directory.iterdir()):
        if source.name.startswith(".") or source == excluded:
            continue
        if source.is_symlink():
            raise ValueError(f"source symlink is not allowed: {source}")
        if source.is_dir():
            yield from visible_files(source, excluded=excluded)
        elif source.is_file():
            yield source
