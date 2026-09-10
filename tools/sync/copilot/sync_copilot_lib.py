from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
import os
import stat

from sync_copilot_discovery import discover
from sync_copilot_mapping import Mapping, render
from sync_copilot_validation import (
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


def synchronize(source: Path, github: Path, mode: str, prune: bool = False) -> Result:
    source = source.absolute()
    github = github.absolute()
    _validate_source(source)
    mappings = discover(source, github)
    errors = validate_before_render(source, github, mappings)
    if errors:
        return Result(0, 0, 0, tuple(errors))
    rendered = {mapping.destination: render(mapping) for mapping in mappings}
    errors = validate_rendered(mappings, rendered)
    if errors:
        return Result(0, 0, 0, tuple(errors))

    # Manifest ownership
    current_owned: frozenset[str] = frozenset(
        mapping.destination.relative_to(github).as_posix() for mapping in mappings
    )
    prior_owned, manifest_errors = _read_manifest(github)
    if manifest_errors:
        return Result(0, 0, 0, tuple(manifest_errors))
    stale_paths: frozenset[str] = prior_owned - current_owned

    # Validate manifest paths before any writes/deletes
    if stale_paths:
        path_errors = _validate_manifest_paths(github, stale_paths, for_prune=prune)
        if path_errors:
            return Result(0, 0, 0, tuple(path_errors))

    # Classify generated file changes (shared across all modes)
    created = updated = unchanged = 0
    classified: list[tuple[Mapping, str, str]] = []
    for mapping in mappings:
        content = rendered[mapping.destination]
        status = _classify(mapping.destination, content)
        if status == "created":
            created += 1
        elif status == "updated":
            updated += 1
        else:
            unchanged += 1
        classified.append((mapping, content, status))

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
            _write_atomic(github, mapping.destination, content)

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
        else:
            stale_changes_apply.append(("stale", f".github/{path_str}"))

    # Write manifest atomically after all writes and pruning succeed
    _write_manifest_atomic(github, current_owned)

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


def _validate_manifest_paths(
    github: Path, paths: frozenset[str], *, for_prune: bool
) -> list[str]:
    errors: list[str] = []
    for path_str in sorted(paths):
        if path_str.startswith("/"):
            errors.append(f"manifest contains absolute path: {path_str}")
            continue
        if ".." in Path(path_str).parts:
            errors.append(f"manifest contains escaping path: {path_str}")
            continue
        if for_prune and (github / path_str).is_symlink():
            errors.append(
                f"manifest path is a symlink, refusing to prune: {github / path_str}"
            )
    return errors


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


def _classify(destination: Path, content: str) -> str:
    if destination.is_symlink():
        return "updated"
    if not destination.exists():
        return "created"
    return "unchanged" if destination.read_text() == content else "updated"


def _write_atomic(github: Path, destination: Path, content: str) -> None:
    errors = validate_destination(github, destination)
    if errors:
        raise ValueError(errors[0])
    mode = (
        stat.S_IMODE(destination.stat().st_mode)
        if destination.exists()
        else 0o644
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w",
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
