from pathlib import Path

from sync_copilot_mapping import Mapping


def discover(claude: Path, github: Path) -> list[Mapping]:
    mappings: list[Mapping] = []
    for source in sorted((claude / "rules").glob("*.md")):
        mappings.append(
            Mapping(
                source,
                github / "instructions" / f"{source.stem}.instructions.md",
                "rule",
            )
        )
    for source in sorted((claude / "agents").glob("*.md")):
        mappings.append(Mapping(source, github / "agents" / source.name, "agent"))
    skills = claude / "skills"
    for directory in sorted(path for path in skills.iterdir() if path.is_dir()):
        if directory.name not in {"_shared", "_local"}:
            _add_skill_mappings(mappings, github, directory, directory.name)
    shared = skills / "_shared"
    _add_tree(mappings, shared / "contracts", github / "prompts/references/_shared")
    _add_tree(mappings, shared / "references", github / "prompts/_shared/references")
    _add_tree(mappings, shared / "templates", github / "prompts/references/_shared")
    _add_aliases(mappings, claude, github)
    destinations = [mapping.destination for mapping in mappings]
    if len(destinations) != len(set(destinations)):
        raise ValueError("source mappings contain destination collisions")
    return mappings


def _add_skill_mappings(
    mappings: list[Mapping], github: Path, directory: Path, skill: str
) -> None:
    main = directory / "SKILL.md"
    if main.is_file():
        mappings.append(
            Mapping(main, github / "prompts" / f"{skill}.prompt.md", "prompt", skill)
        )
    for filename, suffix in (
        ("checker-prompt.md", "checker"),
        ("code-checker-prompt.md", "code-checker"),
    ):
        source = directory / filename
        if source.is_file():
            mappings.append(
                Mapping(
                    source,
                    github / "prompts" / f"{skill}-{suffix}.prompt.md",
                    "prompt",
                    skill,
                )
            )
    references = directory / "references"
    if references.is_dir():
        for source in sorted(references.rglob("*")):
            if _is_visible_file(source, references):
                destination = github / "prompts/references" / skill
                mappings.append(
                    Mapping(
                        source,
                        destination / source.relative_to(references),
                        "reference",
                        skill,
                    )
                )


def _add_tree(mappings: list[Mapping], source_dir: Path, destination: Path) -> None:
    if not source_dir.is_dir():
        return
    for source in sorted(source_dir.rglob("*")):
        if _is_visible_file(source, source_dir):
            mappings.append(
                Mapping(source, destination / source.relative_to(source_dir), "reference")
            )


def _add_aliases(mappings: list[Mapping], source: Path, target: Path) -> None:
    claude = source / "skills"
    github = target / "prompts/references"
    aliases = (
        ("create-rca/references/rca-template.md", "rca-template.md"),
        ("create-spec/references/spec-template.md", "spec-template.md"),
        ("create-validation/references/validation-template.md", "validation-template.md"),
        (
            "create-validation/references/validation-template.md",
            "create-spec/validation-template.md",
        ),
        ("_shared/templates/session-log-template.md", "apply-fix/session-log-template.md"),
        ("_shared/templates/deploy-result-template.md", "apply-fix/deploy-result-template.md"),
    )
    for source_relative, destination_relative in aliases:
        source = claude / source_relative
        if source.is_file():
            mappings.append(Mapping(source, github / destination_relative, "reference"))


def _is_visible_file(source: Path, root: Path) -> bool:
    return source.is_file() and not any(
        part.startswith(".") for part in source.relative_to(root).parts
    )
