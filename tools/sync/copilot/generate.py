#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
import shlex
import sys


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate native Copilot skills, instructions, and agents from Claude files."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="preview changes")
    mode.add_argument("--check", action="store_true", help="fail when mirror drift exists")
    mode.add_argument(
        "--compatibility-report", action="store_true",
        help="print read-only JSON compatibility diagnostics (not runtime verification)",
    )
    parser.add_argument("--prune", action="store_true", help="remove stale generated files")
    parser.add_argument(
        "--skills-mode", choices=("mirror", "native"), default="mirror",
        help="mirror skill bundles (default) or reuse adjacent persistent .claude/skills",
    )
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
    if args.prune and (args.check or args.compatibility_report):
        selected = "--check" if args.check else "--compatibility-report"
        print(f"error: {selected} and --prune cannot be combined", file=sys.stderr)
        return 2
    try:
        from sync_copilot_lib import format_changes, synchronize
    except ModuleNotFoundError as error:
        if error.name != "yaml":
            raise
        requirements = Path(__file__).with_name("requirements.txt")
        print(
            "error: PyYAML is required; install the Copilot sync dependencies with "
            f"python3 -m pip install -r {shlex.quote(str(requirements))}",
            file=sys.stderr,
        )
        return 1
    mode = "check" if args.check else "dry-run" if args.dry_run else "apply"
    try:
        source, target = resolve_roots(args)
        if args.compatibility_report:
            from sync_copilot_compatibility import compatibility_report

            report = compatibility_report(source, target, skills_mode=args.skills_mode)
            print(json.dumps(report, indent=2))
            return 1 if report["errors"] else 0
        print(f"Source: {source}")
        print(f"Target: {target}")
        result = synchronize(
            source, target, mode, prune=args.prune, skills_mode=args.skills_mode
        )
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
