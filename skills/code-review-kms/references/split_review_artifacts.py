#!/usr/bin/env python3
"""Split a unified diff into the ./review-artifacts/artifact-N.patch files the
code-review-kms specialist prompts read.

The manager-hub server names those paths in every specialist prompt but never
creates them and never publishes their file membership, so the dev machine owns
the split. When the server's own artifact planning fails, the returned prompts
degrade to "read ./local-diff.patch" for every lens — this script is how the
scoping is restored locally.

Three modes:

  --list                inventory the diff (path, added/removed lines, bytes).
                        Cheap input for assigning files to lenses without
                        reading the diff body.

  --auto N              write a starter plan grouping files into N buckets by
                        containing directory, every lens reading every bucket. Safe
                        default: chunked reads, no coverage loss.

  --plan <file.json>    split per an explicit plan and validate coverage.

Plan schema:

  {
    "artifacts": {"1": ["src/app/a.ts"], "2": ["server/b.ts"]},
    "lenses":    {"security-reviewer": [1, 2]}          // optional
  }

Keys may also be the server's own pinned artifact keys ("artifact-1", …), which
is how the convergence loop re-cuts a pinned plan against a fixed working tree.
Either form writes artifact-1.patch — a key already carrying the prefix is not
prefixed twice.

Coverage is the load-bearing check: every file in the diff must land in at
least one artifact, and (when "lenses" is given) every artifact must be read by
at least one lens. Either violation exits 2 — a file no lens reads is a defect
nobody can find.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path

FILE_HEADER = re.compile(r"^diff --git (?:\"?a/(?P<a>.+?)\"?) (?:\"?b/(?P<b>.+?)\"?)$")


def parse_diff(text: str) -> "OrderedDict[str, str]":
    """Return {path: full per-file diff section}, in diff order."""
    sections: "OrderedDict[str, str]" = OrderedDict()
    path: str | None = None
    buf: list[str] = []

    def flush() -> None:
        if path is not None:
            sections[path] = "".join(buf)

    for line in text.splitlines(keepends=True):
        if line.startswith("diff --git "):
            flush()
            buf = [line]
            m = FILE_HEADER.match(line.rstrip("\n"))
            if m:
                path = m.group("b") if m.group("b") != "dev/null" else m.group("a")
            else:  # unparseable header — keep the section under a stable key
                path = line.rstrip("\n")
        else:
            buf.append(line)
    flush()
    return sections


def stats(section: str) -> tuple[int, int, int]:
    added = sum(1 for l in section.splitlines() if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in section.splitlines() if l.startswith("-") and not l.startswith("---"))
    return added, removed, len(section.encode("utf-8"))


def artifact_filename(key: str) -> str:
    """Stem for an artifact key, without double-prefixing a server key.

    A locally generated plan keys buckets `1`, `2`, … and the files are named
    `artifact-1.patch`. A plan carrying the server's own pinned keys already has
    them in that form, so re-splitting under it must not yield
    `artifact-artifact-1.patch` — the lenses are handed paths by name.
    """
    return key if key.startswith("artifact-") else f"artifact-{key}"


def group_key(path: str) -> str:
    """Group by containing directory — keeps a component's .ts/.html/.spec together."""
    parent = path.rsplit("/", 1)[0] if "/" in path else ""
    return parent or path


def auto_plan(sections, n: int) -> dict:
    """Group by containing directory, then pack groups into n buckets by byte size."""
    groups: dict[str, list[str]] = OrderedDict()
    for path in sections:
        groups.setdefault(group_key(path), []).append(path)

    buckets: list[list[str]] = [[] for _ in range(n)]
    sizes = [0] * n
    for _, paths in sorted(groups.items(), key=lambda kv: -sum(stats(sections[p])[2] for p in kv[1])):
        i = sizes.index(min(sizes))
        buckets[i].extend(paths)
        sizes[i] += sum(stats(sections[p])[2] for p in paths)

    return {"artifacts": {str(i + 1): b for i, b in enumerate(buckets) if b}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--diff", default="local-diff.patch", help="unified diff to split (default: local-diff.patch)")
    ap.add_argument("--out-dir", default="review-artifacts", help="output dir (default: review-artifacts)")
    ap.add_argument("--plan", help="plan JSON: {\"artifacts\": {\"1\": [paths]}, \"lenses\": {...}}")
    ap.add_argument("--auto", type=int, metavar="N", help="generate an N-bucket plan instead of reading one")
    ap.add_argument("--list", action="store_true", help="print the changed-file inventory and exit")
    args = ap.parse_args()

    diff_path = Path(args.diff)
    if not diff_path.is_file():
        print(f"ERROR: diff not found: {diff_path}", file=sys.stderr)
        return 1
    sections = parse_diff(diff_path.read_text(encoding="utf-8", errors="replace"))
    if not sections:
        print(f"ERROR: no file sections parsed from {diff_path} (empty or not a unified diff)", file=sys.stderr)
        return 1

    if args.list:
        print(f"{len(sections)} changed file(s) in {diff_path}:")
        for path, section in sections.items():
            a, r, b = stats(section)
            print(f"  +{a:<5} -{r:<5} {b:>7}B  {path}")
        return 0

    if args.auto:
        plan = auto_plan(sections, args.auto)
    elif args.plan:
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    else:
        print("ERROR: pass --plan, --auto N, or --list", file=sys.stderr)
        return 1

    artifacts = {str(k): list(v) for k, v in plan.get("artifacts", {}).items()}
    if not artifacts:
        print("ERROR: plan has no artifacts", file=sys.stderr)
        return 1

    unknown = sorted({p for paths in artifacts.values() for p in paths} - set(sections))
    assigned = {p for paths in artifacts.values() for p in paths}
    unassigned = [p for p in sections if p not in assigned]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for key in sorted(artifacts, key=lambda k: (len(k), k)):
        body = "".join(sections[p] for p in artifacts[key] if p in sections)
        target = out_dir / f"{artifact_filename(key)}.patch"
        target.write_text(body, encoding="utf-8")
        written.append((target, len(artifacts[key]), len(body.encode("utf-8"))))

    lenses = plan.get("lenses") or {}
    read_artifacts = {str(a) for ids in lenses.values() for a in ids}
    unread = sorted(set(artifacts) - read_artifacts) if lenses else []

    (out_dir / "artifact-plan.json").write_text(
        json.dumps({"diff": str(diff_path), "artifacts": artifacts, "lenses": lenses}, indent=2) + "\n",
        encoding="utf-8",
    )

    for target, nfiles, nbytes in written:
        print(f"wrote {target}  ({nfiles} file(s), {nbytes}B)")
    print(f"plan recorded at {out_dir / 'artifact-plan.json'}")

    failed = False
    if unassigned:
        print("ERROR: files in the diff assigned to NO artifact — every lens would be blind to them:", file=sys.stderr)
        for p in unassigned:
            print(f"  {p}", file=sys.stderr)
        failed = True
    if unread:
        print(f"ERROR: artifact(s) {', '.join(unread)} are read by no lens — assign them or drop them.", file=sys.stderr)
        failed = True
    if unknown:
        print("WARNING: plan names paths absent from the diff (typo, or a stale plan):", file=sys.stderr)
        for p in unknown:
            print(f"  {p}", file=sys.stderr)

    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
