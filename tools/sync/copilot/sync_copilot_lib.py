from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
import os
import stat

from sync_copilot_discovery import discover
from sync_copilot_mapping import Mapping, render
from sync_copilot_native import validate_native_layout, validate_native_shadows
from sync_copilot_validation import (
    case_mismatch,
    validate_before_render,
    validate_destination,
    validate_rendered,
)

MANIFEST_RELPATH = ".invocare-generated-manifest"


@dataclass(frozen=True)
class Result:
    created: int
    updated: int
    unchanged: int
    errors: tuple[str, ...]
    changes: tuple[tuple[str, str], ...] = ()
    stale: int = 0
    removed: int = 0


def synchronize(
    source: Path, github: Path, mode: str, prune: bool = False,
    *, skills_mode: str = "mirror",
) -> Result:
    source = source.absolute()
    github = github.absolute()
    if skills_mode not in {"mirror", "native"}:
        raise ValueError(f"unknown skills mode: {skills_mode}")
    if skills_mode == "native":
        validate_native_layout(source, github)
    _validate_source(source)
    mappings = discover(source, github, skills_mode=skills_mode)
    errors = validate_before_render(source, github, mappings)
    if errors:
        return Result(0, 0, 0, tuple(errors))
    path_mappings = {
        f".claude/{mapping.source.relative_to(source).as_posix()}":
        f".github/{mapping.destination.relative_to(github).as_posix()}"
        for mapping in mappings if mapping.generated and mapping.kind in {"rule", "agent"}
    }
    rendered = {
        mapping.destination: render(
            mapping, source, skills_mode=skills_mode, path_mappings=path_mappings
        )
        for mapping in mappings
    }
    errors = validate_rendered(mappings, rendered)
    if errors:
        return Result(0, 0, 0, tuple(errors))

    # Manifest ownership
    generated = [mapping for mapping in mappings if mapping.generated]
    current_owned: frozenset[str] = frozenset(
        mapping.destination.relative_to(github).as_posix() for mapping in generated
    )
    prior_owned, manifest_errors = _read_manifest(github)
    if manifest_errors:
        return Result(0, 0, 0, tuple(manifest_errors))
    stale_paths: frozenset[str] = prior_owned - current_owned

    # Validate manifest paths before any writes/deletes
    if stale_paths:
        path_errors = _validate_manifest_paths(github, stale_paths)
        if path_errors:
            return Result(0, 0, 0, tuple(path_errors))
        aliases, alias_errors = _reconcile_case_aliases(github, current_owned, stale_paths)
        if alias_errors:
            return Result(0, 0, 0, tuple(alias_errors))
        prior_owned |= frozenset(aliases.values())
        stale_paths -= frozenset(aliases)

    if skills_mode == "native":
        names = {mapping.skill for mapping in mappings if mapping.skill is not None}
        errors.extend(
            validate_native_shadows(source, github, names, prior_owned, prune=prune)
        )
        if errors:
            return Result(0, 0, 0, tuple(errors))

    # Classify generated file changes (shared across all modes)
    created = updated = unchanged = 0
    classified: list[tuple[Mapping, bytes, str]] = []
    for mapping in generated:
        content = rendered[mapping.destination]
        status = _classify(mapping.destination, content)
        relative = mapping.destination.relative_to(github)
        if (
            relative.as_posix() not in prior_owned
            and status == "updated"
        ):
            category = "native skill" if relative.parts[0] == "skills" else mapping.kind
            errors.append(
                f"unmanaged {category} file would be overwritten: {mapping.destination}; "
                "reconcile it in the source/profile or move it aside before syncing"
            )
        if status == "created":
            created += 1
        elif status == "updated":
            updated += 1
        else:
            unchanged += 1
        classified.append((mapping, content, status))

    if errors:
        return Result(0, 0, 0, tuple(errors))

    generated_changes: list[tuple[str, str]] = [
        (status, _display_path(github, mapping.destination))
        for mapping, _, status in classified
        if status != "unchanged"
    ]

    if mode == "check":
        check_errors: list[str] = []
        if generated_changes:
            check_errors.append(
                f"drift detected in {len(generated_changes)} generated file(s)"
            )
        if stale_paths:
            check_errors.append(
                f"{len(stale_paths)} stale generated file(s) found in manifest"
            )
        stale_changes_check = [
            ("stale", f".github/{p}") for p in sorted(stale_paths)
        ]
        all_changes = generated_changes + stale_changes_check
        stale_count = len(stale_paths)
        if check_errors:
            return Result(
                created, updated, unchanged,
                tuple(check_errors),
                tuple(all_changes),
                stale=stale_count,
            )
        return Result(created, updated, unchanged, (), tuple(all_changes), stale=stale_count)

    if mode == "dry-run":
        stale_changes_dry: list[tuple[str, str]] = []
        for path_str in sorted(stale_paths):
            stale_file = github / path_str
            if prune and stale_file.is_file() and not stale_file.is_symlink():
                stale_changes_dry.append(("removed", f".github/{path_str}"))
            else:
                stale_changes_dry.append(("stale", f".github/{path_str}"))
        all_changes = generated_changes + stale_changes_dry
        stale_count = sum(1 for s, _ in stale_changes_dry if s == "stale")
        removed_count = sum(1 for s, _ in stale_changes_dry if s == "removed")
        return Result(
            created, updated, unchanged, (), tuple(all_changes),
            stale=stale_count, removed=removed_count,
        )

    # apply mode: write generated files first
    for mapping, content, status in classified:
        if status != "unchanged":
            _write_atomic(
                github, mapping.destination, content,
                source_mode=stat.S_IMODE(mapping.source.stat().st_mode),
            )

    # Prune or collect stale changes
    stale_changes_apply: list[tuple[str, str]] = []
    removed_count = 0
    for path_str in sorted(stale_paths):
        stale_file = github / path_str
        if prune and stale_file.is_file() and not stale_file.is_symlink():
            stale_file.unlink()
            removed_count += 1
            stale_changes_apply.append(("removed", f".github/{path_str}"))
            _remove_empty_parents(stale_file.parent, github)
        elif not prune:
            stale_changes_apply.append(("stale", f".github/{path_str}"))

    # Write manifest atomically after all writes and pruning succeed
    github.mkdir(parents=True, exist_ok=True)
    _write_manifest_atomic(github, current_owned | (stale_paths if not prune else frozenset()))

    all_changes = generated_changes + stale_changes_apply
    stale_count = sum(1 for s, _ in stale_changes_apply if s == "stale")
    return Result(
        created, updated, unchanged, (), tuple(all_changes),
        stale=stale_count, removed=removed_count,
    )


def format_changes(result: Result, mode: str) -> str:
    stale_suffix = f", {result.stale} stale" if result.stale else ""
    removed_suffix = f", {result.removed} removed" if result.removed else ""
    if mode == "dry-run":
        summary = (
            f"would create {result.created}, would update {result.updated}; "
            f"{result.unchanged} unchanged{stale_suffix}\n"
        )
    else:
        summary = (
            f"{result.created} created, {result.updated} updated, "
            f"{result.unchanged} unchanged{stale_suffix}{removed_suffix}\n"
        )
    details = "".join(_format_detail(status, path, mode) for status, path in result.changes)
    return summary + details


def _format_detail(status: str, path: str, mode: str) -> str:
    if mode == "dry-run":
        if status == "created":
            return f"  would create: {path}\n"
        if status == "updated":
            return f"  would update: {path}\n"
        if status == "removed":
            return f"  would remove: {path}\n"
        return f"  {status}: {path}\n"
    return f"  {status}: {path}\n"


def _read_manifest(github: Path) -> tuple[frozenset[str], list[str]]:
    manifest = github / MANIFEST_RELPATH
    if not manifest.exists():
        return frozenset(), []
    if manifest.is_symlink():
        return frozenset(), [f"manifest is a symlink: {manifest}"]
    try:
        lines = manifest.read_text().splitlines()
    except OSError as error:
        return frozenset(), [f"cannot read manifest: {error}"]
    paths = frozenset(line.strip() for line in lines if line.strip())
    return paths, []


def _validate_manifest_paths(github: Path, paths: frozenset[str]) -> list[str]:
    errors: list[str] = []
    for path_str in sorted(paths):
        if path_str.startswith("/"):
            errors.append(f"manifest contains absolute path: {path_str}")
            continue
        if ".." in Path(path_str).parts:
            errors.append(f"manifest contains escaping path: {path_str}")
            continue
        errors.extend(validate_destination(github, github / path_str))
        if (github / path_str).is_dir():
            errors.append(f"manifest path must be a file: {github / path_str}")
    return errors


def _reconcile_case_aliases(
    github: Path, current: frozenset[str], stale: frozenset[str]
) -> tuple[dict[str, str], list[str]]:
    by_identity: dict[tuple[int, int], list[str]] = {}
    for relative in sorted(current):
        path = github / relative
        if path.is_file():
            info = path.stat()
            by_identity.setdefault((info.st_dev, info.st_ino), []).append(relative)

    aliases: dict[str, str] = {}
    errors: list[str] = []
    for relative in sorted(stale):
        path = github / relative
        if not path.is_file():
            continue
        info = path.stat()
        matches = by_identity.get((info.st_dev, info.st_ino), [])
        candidates = [
            match for match in matches
            if case_mismatch(github, path) or case_mismatch(github, github / match)
        ]
        if len(candidates) > 1:
            errors.append(f"ambiguous case-only rename aliases multiple active files: {path}")
        elif candidates:
            active = candidates[0]
            if case_mismatch(github, github / active):
                errors.append(
                    f"destination casing differs (case-only rename): {github / active}; "
                    "rename through a temporary name to match the source before syncing"
                )
            else:
                # An obsolete spelling is not a separate file to unlink.
                aliases[relative] = active
    return aliases, errors


def _write_manifest_atomic(github: Path, paths: frozenset[str]) -> None:
    manifest = github / MANIFEST_RELPATH
    content = "\n".join(sorted(paths)) + "\n" if paths else ""
    with NamedTemporaryFile(
        "w",
        dir=github,
        prefix=f".{MANIFEST_RELPATH}.",
        delete=False,
    ) as handle:
        tmp = Path(handle.name)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(tmp, manifest)
    finally:
        if tmp.exists():
            tmp.unlink()


def _remove_empty_parents(directory: Path, stop_at: Path) -> None:
    """Remove directory and its empty ancestors up to (not including) stop_at."""
    current = directory.absolute()
    stop = stop_at.absolute()
    while current != stop:
        try:
            current.relative_to(stop)
        except ValueError:
            break
        try:
            current.rmdir()
            current = current.parent
        except OSError:
            break


def _validate_source(source: Path) -> None:
    required = (
        source / "rules",
        source / "skills",
        source / "agents",
    )
    symlinked = [str(path) for path in (source, *required) if path.is_symlink()]
    if symlinked:
        raise ValueError(f"source symlink is not allowed: {', '.join(symlinked)}")
    missing = [str(path) for path in required if not path.is_dir()]
    if missing:
        raise ValueError(f"source is missing required directories: {', '.join(missing)}")


def _display_path(github: Path, destination: Path) -> str:
    return f".github/{destination.relative_to(github).as_posix()}"


def _classify(destination: Path, content: bytes) -> str:
    if destination.is_symlink():
        return "updated"
    if not destination.exists():
        return "created"
    return "unchanged" if destination.read_bytes() == content else "updated"


def _write_atomic(
    github: Path, destination: Path, content: bytes, *, source_mode: int
) -> None:
    errors = validate_destination(
        github, destination,
        check_case=destination.relative_to(github).parts[0] == "skills",
    )
    if errors:
        raise ValueError(errors[0])
    mode = (
        stat.S_IMODE(destination.stat().st_mode)
        if destination.exists()
        else source_mode
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "wb",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.chmod(mode)
    try:
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
