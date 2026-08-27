#!/usr/bin/env python3

import argparse
from pathlib import Path
import sys

from sync_copilot_lib import format_changes, synchronize


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Copilot .github files from authoritative Claude files."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="preview changes")
    mode.add_argument("--check", action="store_true", help="fail when mirror drift exists")
    parser.add_argument("--prune", action="store_true", help="remove stale generated files")
    parser.add_argument("workspace", nargs="?", help="workspace root")
    parser.add_argument("--source", help="source .claude directory")
    parser.add_argument("--target", help="target .github directory")
    return parser.parse_args(argv)


def resolve_workspace(raw: str | None) -> Path:
    if raw:
        return Path(raw).expanduser().resolve()
    current = Path.cwd().resolve()
    if (current / ".claude").is_dir() and (current / ".github").is_dir():
        return current
    for ancestor in Path(__file__).resolve().parents:
        if (ancestor / ".claude").is_dir() and (ancestor / ".github").is_dir():
            return ancestor
    return current


def resolve_roots(args: argparse.Namespace) -> tuple[Path, Path]:
    if bool(args.source) != bool(args.target):
        raise ValueError("--source and --target must be provided together")
    if args.source:
        if args.workspace:
            raise ValueError("workspace cannot be combined with --source and --target")
        source = Path(args.source).expanduser().absolute()
        target = Path(args.target).expanduser().absolute()
        return source, target
    workspace = resolve_workspace(args.workspace)
    return workspace / ".claude", workspace / ".github"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.check and args.prune:
        print("error: --check and --prune cannot be combined", file=sys.stderr)
        return 2
    mode = "check" if args.check else "dry-run" if args.dry_run else "apply"
    try:
        source, target = resolve_roots(args)
        print(f"Source: {source}")
        print(f"Target: {target}")
        result = synchronize(source, target, mode, prune=args.prune)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    if result.errors:
        if args.check and result.changes:
            print(format_changes(result, mode), end="")
        for error in result.errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print(format_changes(result, mode), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
