"""Read-only configuration diagnostics, not a client runtime verification."""

from pathlib import Path
import re

from sync_copilot_discovery import discover
from sync_copilot_lib import synchronize
from sync_copilot_mapping import is_markdown
from sync_copilot_metadata import agent_metadata, rule_metadata
from sync_copilot_yaml import load_yaml_mapping, split_frontmatter


def compatibility_report(
    source: Path, github: Path, *, skills_mode: str = "mirror"
) -> dict[str, object]:
    source = source.absolute()
    github = github.absolute()
    workspace = github.parent
    errors: list[str] = []
    warnings = [
        {
            "code": "CLIENT_SCOPE",
            "message": "This report targets Copilot CLI 1.0.83, not equivalent VS Code, "
            "cloud agent, or Claude Code runtime behavior.",
        },
        {
            "code": "DISCOVERY_RUNTIME_UNVERIFIED",
            "message": "Directory trust, added roots, duplicate names outside this "
            "workspace, and the active client version need runtime confirmation. "
            "CLAUDE.md, AGENTS.md, and other instruction imports can load governance "
            "independently of generated applyTo scopes.",
        },
        {
            "code": "MCP_RUNTIME_UNVERIFIED",
            "message": "Declared MCP tools are requirements, not evidence that servers "
            "are registered, authenticated, available, or approved.",
        },
        {
            "code": "HOOK_RUNTIME_UNVERIFIED",
            "message": "Governance text is not hook enforcement. Runtime scripts, event "
            "payloads, failure handling, and active hooks must be confirmed separately. "
            "Do not duplicate hooks already loaded from Claude settings.",
        },
    ]
    report: dict[str, object] = {
        "schema_version": 1,
        "client": "copilot-cli",
        "baseline_version": "1.0.83",
        "read_only": True,
        "source": str(source),
        "target": str(github),
        "skills_mode": skills_mode,
        "static_status": "blocked",
        "runtime_verification": "not_performed",
        "runtime_checks": [
            "model and custom agent availability",
            "MCP registration, authentication, and tool availability",
            "tool permissions and approvals, including shell access",
            "skill invocation controls and directory discovery",
            "hook payloads, exit handling, and enforcement",
        ],
        "counts": None,
        "agents": [],
        "rules": [],
        "skills": [],
        "discovery": {
            "precedence": [".github/skills", ".agents/skills", ".claude/skills"],
            "guidance": (
                "Native .claude/skills discovery is for this project root. It is not "
                "a guarantee of added-root discovery from a child repository; keep "
                "the default .github mirror for central umbrella deployment."
                if skills_mode == "native" else
                "The .github mirror supports central deployment. Start in the "
                "workspace or explicitly add/trust the umbrella directory, then "
                "inspect the active skill and agent copies in the client."
            ),
        },
        "warnings": warnings,
        "errors": errors,
    }
    mcp: dict[str, object] = {
        "configuration": "not_inspected",
        "availability": "not_verified",
        "required_tools": [],
        "shared_claude_references": [],
        "project_files": {
            ".mcp.json": (workspace / ".mcp.json").is_file(),
            f"{github.name}/mcp.json": (github / "mcp.json").is_file(),
        },
        "guidance": "Project files are only presence indicators; personal or plugin "
        "configuration may provide servers. Configuration contents and credentials "
        "are never read. Claude tool spellings in shared bodies require corresponding "
        "Copilot bindings; they are not automatically provisioned.",
    }
    hooks: dict[str, object] = {
        "configuration": "not_converted",
        "enforcement": "not_verified",
        "exporter_installs_runtime": False,
        "project_settings": {
            str(path.relative_to(workspace)): path.is_file()
            for path in (
                workspace / ".claude/settings.json",
                workspace / ".claude/settings.local.json",
                github / "copilot/settings.json",
                github / "copilot/settings.local.json",
            )
        },
        "referenced_scripts": [],
    }
    report["mcp"] = mcp
    report["hooks"] = hooks

    try:
        preview = synchronize(source, github, "dry-run", skills_mode=skills_mode)
        errors.extend(preview.errors)
        report["sync_preview"] = {
            "created": preview.created,
            "updated": preview.updated,
            "unchanged": preview.unchanged,
            "stale": preview.stale,
        }
        if errors:
            return report
        mappings = discover(source, github, skills_mode=skills_mode)
        report["counts"] = {
            label: sum(mapping.kind == kind for mapping in mappings)
            for label, kind in (
                ("agents", "agent"), ("rules", "rule"),
                ("skills", "skill"), ("resources", "resource"),
            )
        }
        agents: list[dict[str, object]] = []
        rules: list[dict[str, object]] = []
        skills: list[dict[str, object]] = []
        required_tools: set[str] = set()
        shared_references: set[str] = set()
        scripts: set[str] = set()
        for mapping in mappings:
            if not is_markdown(mapping.source):
                continue
            text = mapping.source.read_text(encoding="utf-8")
            shared_references.update(
                re.findall(r"\bmcp__[A-Za-z0-9_-]+__[A-Za-z0-9_]+\b", text)
            )
            scripts.update(
                re.findall(
                    r"\.claude/(?:scripts|hooks)/[A-Za-z0-9_./-]+\.(?:sh|py|js)\b",
                    text,
                )
            )
            if mapping.kind == "agent":
                metadata = agent_metadata(source, mapping.source, text)
                profile = source / "copilot/agents" / f"{mapping.source.stem}.yaml"
                tools = metadata["tools"]
                required_tools.update(tool for tool in tools if "/" in tool)
                agents.append({
                    "name": mapping.source.stem,
                    "profile": profile.relative_to(source).as_posix() if profile.is_file() else None,
                    "location": str(mapping.destination),
                    "target": metadata.get("target"),
                    "invocation": {
                        field: metadata[field]
                        for field in ("user-invocable", "disable-model-invocation", "infer")
                        if field in metadata
                    },
                    "model": {
                        "policy": "explicit" if metadata.get("model") else "session",
                        "id": metadata.get("model"),
                    },
                    "tools": tools,
                })
                if metadata.get("target") == "github-copilot":
                    warnings.append({
                        "code": "AGENT_TARGET_MISMATCH",
                        "message": f"{mapping.source.stem}: target is github-copilot; "
                        "this agent is not targeted at Copilot CLI.",
                    })
            elif mapping.kind == "rule":
                metadata = rule_metadata(mapping.source, text)
                rules.append({
                    "source": mapping.source.relative_to(source).as_posix(),
                    "location": str(mapping.destination),
                    "applyTo": metadata["applyTo"],
                })
            elif mapping.kind == "skill":
                frontmatter, _ = split_frontmatter(text)
                metadata = load_yaml_mapping(frontmatter[4:-4], mapping.source)
                extensions = sorted(
                    {"context", "agent", "hooks", "model"}.intersection(metadata)
                )
                skills.append({
                    "name": mapping.skill,
                    "location": str(mapping.destination),
                    "user_invocable": metadata.get("user-invocable", True),
                    "model_invocable": not metadata.get("disable-model-invocation", False),
                    "argument_hint": metadata.get("argument-hint"),
                    "extensions": extensions,
                })
                if extensions:
                    warnings.append({
                        "code": "SKILL_EXECUTION_EXTENSIONS",
                        "message": f"{mapping.skill}: {', '.join(extensions)} are "
                        "copied unchanged; their Claude execution semantics are not "
                        "translated or runtime-verified.",
                    })
                if "allowed-tools" in metadata:
                    warnings.append({
                        "code": "SKILL_TOOL_PREAPPROVAL",
                        "message": f"{mapping.skill}: allowed-tools is skill "
                        "preapproval, not an agent's restrictive tool list or a "
                        "substitute for runtime permissions.",
                    })
                if re.search(r"\$(?:ARGUMENTS\b|\d+\b)|!`", text):
                    warnings.append({
                        "code": "SKILL_DYNAMIC_CONTENT",
                        "message": f"{mapping.skill}: argument substitution or "
                        "dynamic shell content requires client-specific review; "
                        "the exporter does not execute or translate it.",
                    })
        report["agents"] = agents
        report["rules"] = rules
        report["skills"] = skills
        mcp["required_tools"] = sorted(required_tools)
        mcp["shared_claude_references"] = sorted(shared_references)
        hooks["referenced_scripts"] = [
            {"path": path, "present": (workspace / path).is_file()}
            for path in sorted(scripts)
        ]
        if github.name != ".github":
            warnings.append({
                "code": "NONSTANDARD_TARGET",
                "message": "The target is not named .github; generating files here "
                "does not establish native client discovery.",
            })
        report["static_status"] = "valid"
    except (OSError, ValueError) as error:
        errors.append(str(error))
    return report
