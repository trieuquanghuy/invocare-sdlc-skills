"""Fail-closed conversion of source metadata and explicit Copilot agent profiles."""

from pathlib import Path
import re
import stat

from sync_copilot_yaml import load_yaml_mapping, split_frontmatter


_AGENT_FIELDS = {
    "name", "description", "tools", "model", "target",
    "user-invocable", "disable-model-invocation", "infer",
}
_RULE_FIELDS = {"description", "paths"}

# https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference#tool-availability-values
_CLI_TOOLS = {
    "bash", "powershell", "list_bash", "list_powershell", "read_bash",
    "read_powershell", "stop_bash", "stop_powershell", "write_bash", "write_powershell",
    "apply_patch", "create", "edit", "view", "list_agents", "read_agent", "task",
    "write_agent", "ask_user", "glob", "grep", "rg", "skill", "web_fetch",
}
# https://docs.github.com/en/copilot/reference/custom-agents-configuration#tool-aliases
_TOOL_ALIASES = {
    "execute", "shell", "bash", "powershell", "read", "notebookread",
    "edit", "multiedit", "write", "notebookedit", "search", "grep", "glob",
    "agent", "custom-agent", "task", "runsubagent", "web", "websearch", "webfetch",
    "todo", "todowrite",
}
_MCP_TOOL = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*/(?:[A-Za-z0-9_][A-Za-z0-9_.-]*|\*)")
_MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_CLAUDE_MODEL_ALIASES = {"sonnet", "opus", "haiku", "opusplan", "default", "inherit"}


def _source_metadata(source: Path, text: str) -> dict[str, object]:
    frontmatter, _ = split_frontmatter(text)
    if frontmatter:
        return load_yaml_mapping(frontmatter[4:-4], source)
    if re.match(r"^\ufeff?---[ \t]*(?:\r?\n|$)", text):
        raise ValueError(f"{source}: unclosed or unsupported frontmatter delimiters")
    return {}


def _check_fields(metadata: dict[str, object], allowed: set[str], path: Path) -> None:
    unknown = metadata.keys() - allowed
    if unknown:
        raise ValueError(
            f"{path}: unsupported metadata fields: {', '.join(sorted(unknown))}; "
            "a Copilot metadata profile cannot implement unsupported runtime behavior"
        )


def _nonempty_string(value: object, path: Path, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: {field} must be a non-empty string")
    return value


def _agent_profile(root: Path, source: Path) -> tuple[Path, dict[str, object]] | None:
    profile = root / "copilot" / "agents" / f"{source.stem}.yaml"
    for path in (root / "copilot", root / "copilot" / "agents", profile):
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError:
            return None
        except OSError as error:
            raise ValueError(f"{path}: cannot inspect Copilot profile path: {error}") from error
        if stat.S_ISLNK(mode):
            raise ValueError(f"{path}: Copilot profile symlink is not allowed")
        if path == profile:
            if not stat.S_ISREG(mode):
                raise ValueError(f"{path}: Copilot agent profile must be a regular file")
        elif not stat.S_ISDIR(mode):
            raise ValueError(f"{path}: Copilot profile parent must be a directory")
    try:
        text = profile.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ValueError(f"{profile}: cannot read Copilot agent profile: {error}") from error
    return profile, load_yaml_mapping(text, profile)


def _tools(value: object, path: Path) -> list[str]:
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, list):
        raise ValueError(f"{path}: tools must be an explicit list or comma-separated string")
    tools = []
    for item in value:
        tool = _nonempty_string(item, path, "tools entry").strip()
        if tool.startswith("mcp__"):
            raise ValueError(
                f"{path}: unconverted Claude MCP tool {tool!r}; "
                "choose an explicit Copilot server/tool identifier in a profile"
            )
        if not (
            tool == "*" or tool in _CLI_TOOLS or tool.lower() in _TOOL_ALIASES
            or _MCP_TOOL.fullmatch(tool)
        ):
            raise ValueError(
                f"{path}: unrecognized Copilot tool {tool!r}; "
                "use a documented CLI tool, alias, or explicit server/tool identifier"
            )
        tools.append(tool)
    return tools


def agent_metadata(root: Path, source: Path, text: str) -> dict[str, object]:
    metadata = _source_metadata(source, text)
    _check_fields(metadata, _AGENT_FIELDS, source)
    profile = _agent_profile(root, source)
    overrides = {}
    profile_path = source
    if profile is not None:
        profile_path, overrides = profile
        _check_fields(overrides, _AGENT_FIELDS, profile_path)
        for field in ("tools", "model"):
            if field not in overrides:
                raise ValueError(f"{profile_path}: agent profile requires explicit {field}")
        metadata.update(overrides)

    def origin(field: str) -> Path:
        return profile_path if field in overrides else source

    metadata["description"] = _nonempty_string(
        metadata.get("description"), origin("description"), "description"
    )
    if "name" in metadata:
        _nonempty_string(metadata["name"], origin("name"), "name")
    if "tools" not in metadata:
        raise ValueError(f"{source}: agent requires explicit tools; use [] to grant none")
    metadata["tools"] = _tools(metadata["tools"], origin("tools"))
    if "target" in metadata and metadata["target"] not in ("copilot-cli", "github-copilot"):
        raise ValueError(
            f"{origin('target')}: target must be copilot-cli or github-copilot"
        )
    for field in ("user-invocable", "disable-model-invocation", "infer"):
        if field in metadata and not isinstance(metadata[field], bool):
            raise ValueError(f"{origin(field)}: {field} must be a boolean")

    model = metadata.get("model")
    if model is None or (profile is None and model == "inherit"):
        metadata.pop("model", None)
    elif (
        not isinstance(model, str)
        or not _MODEL_ID.fullmatch(model)
        or model.lower() in _CLAUDE_MODEL_ALIASES
    ):
        raise ValueError(
            f"{origin('model')}: model must be an explicit Copilot model ID, not a Claude alias; "
            "use model: null in a profile to inherit the Copilot session model"
        )
    return metadata


def _expand_braces(pattern: str, source: Path, depth: int = 0) -> list[str]:
    if depth > 32:
        raise ValueError(f"{source}: paths brace nesting exceeds the supported limit")
    opening = pattern.find("{")
    if opening < 0:
        if "}" in pattern or "," in pattern:
            raise ValueError(f"{source}: paths has malformed braces or a comma outside braces")
        return [pattern]
    prefix = pattern[:opening]
    if "}" in prefix or "," in prefix:
        raise ValueError(f"{source}: paths has malformed braces or a comma outside braces")
    level = 0
    start = opening + 1
    alternatives = []
    for index in range(opening, len(pattern)):
        character = pattern[index]
        if character == "{":
            level += 1
        elif character == "}":
            level -= 1
            if level == 0:
                alternatives.append(pattern[start:index])
                break
        elif character == "," and level == 1:
            alternatives.append(pattern[start:index])
            start = index + 1
    else:
        raise ValueError(f"{source}: paths has unclosed braces")
    if len(alternatives) < 2 or any(not item for item in alternatives):
        raise ValueError(f"{source}: paths braces need at least two non-empty alternatives")
    suffixes = _expand_braces(pattern[index + 1 :], source, depth + 1)
    expanded = []
    for alternative in alternatives:
        for middle in _expand_braces(alternative, source, depth + 1):
            for suffix in suffixes:
                expanded.append(prefix + middle + suffix)
                if len(expanded) > 256:
                    raise ValueError(f"{source}: paths brace expansion exceeds 256 patterns")
    return expanded


def _rule_paths(value: object, source: Path) -> str:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not value:
        raise ValueError(f"{source}: paths must be a non-empty string or list of strings")
    patterns = []
    for item in value:
        pattern = _nonempty_string(item, source, "paths")
        if pattern != pattern.strip() or not re.fullmatch(r"[\w .@+*/{},-]+", pattern):
            raise ValueError(f"{source}: paths contains an unsupported glob: {pattern!r}")
        for expanded in _expand_braces(pattern, source):
            segments = expanded.split("/")
            if any(
                not segment or segment in {".", ".."} or segment != segment.strip()
                or ("**" in segment and segment != "**")
                for segment in segments
            ):
                raise ValueError(
                    f"{source}: paths must use positive relative globs without escaping "
                    f"segments or embedded globstars: {expanded!r}"
                )
            patterns.append(expanded)
    return ",".join(patterns)


def rule_metadata(source: Path, text: str) -> dict[str, object]:
    metadata = _source_metadata(source, text)
    _check_fields(metadata, _RULE_FIELDS, source)
    description = _nonempty_string(
        metadata.get("description", f"{source.stem} governance rules."),
        source, "description",
    )
    apply_to = _rule_paths(metadata["paths"], source) if "paths" in metadata else "**"
    return {"applyTo": apply_to, "description": description}
