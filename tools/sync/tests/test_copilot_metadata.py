#!/usr/bin/env python3

import __future__
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

import yaml


SYNC_DIR = Path(__file__).resolve().parents[1]
ROOT = SYNC_DIR.parents[1]
HELPERS = SYNC_DIR / "copilot"
sys.path.insert(0, str(HELPERS))


def markdown(metadata):
    return "---\n" + yaml.safe_dump(metadata, sort_keys=False) + "---\n\nBody.\n"


class CopilotAnnotationCompatibilityTest(unittest.TestCase):
    def test_union_annotations_remain_deferred_through_the_import_chain(self):
        for name in (
            "generate.py", "sync_copilot_discovery.py", "sync_copilot_mapping.py",
            "sync_copilot_metadata.py", "sync_copilot_validation.py",
        ):
            with self.subTest(module=name):
                path = HELPERS / name
                code = compile(
                    path.read_text(encoding="utf-8"), str(path), "exec",
                    dont_inherit=True,
                )
                self.assertTrue(
                    code.co_flags & __future__.annotations.compiler_flag,
                    f"{name} must defer union annotations for Python 3.9 imports",
                )


class HelperTestCase(unittest.TestCase):
    def setUp(self):
        for module in ("sync_copilot_yaml", "sync_copilot_metadata"):
            self.assertTrue(
                (HELPERS / f"{module}.py").is_file(),
                f"{module} helper has not been implemented",
            )
        from sync_copilot_metadata import agent_metadata, rule_metadata
        from sync_copilot_yaml import load_yaml_mapping, split_frontmatter

        self.agent_metadata = agent_metadata
        self.rule_metadata = rule_metadata
        self.load_yaml_mapping = load_yaml_mapping
        self.split_frontmatter = split_frontmatter


class YamlHelpersTest(HelperTestCase):
    def test_split_frontmatter_preserves_original_delimiter_and_body_behavior(self):
        cases = (
            ("Body.\n", "", "Body.\n"),
            ("---\na: b\n---\n\nBody.\n", "---\na: b\n---\n", "\nBody.\n"),
            ("---\na: b\n---\n---\n", "---\na: b\n---\n", "---\n"),
            ("---\n\n---\nBody.\n", "---\n\n---\n", "Body.\n"),
            ("---\n---\n", "", "---\n---\n"),
            ("---\na: b\n---", "", "---\na: b\n---"),
            ("---\r\na: b\r\n---\r\nBody.\r\n", "", "---\r\na: b\r\n---\r\nBody.\r\n"),
            (" ---\na: b\n---\n", "", " ---\na: b\n---\n"),
        )
        for text, frontmatter, body in cases:
            with self.subTest(text=text):
                self.assertEqual(self.split_frontmatter(text), (frontmatter, body))

    def test_raw_yaml_mapping_preserves_types_and_multiline_values(self):
        self.assertEqual(
            self.load_yaml_mapping(
                "description: |\n  First line.\n  Second line.\n"
                "tools: []\nmodel: null\nuser-invocable: false\n",
                Path("profile.yaml"),
            ),
            {
                "description": "First line.\nSecond line.\n",
                "tools": [],
                "model": None,
                "user-invocable": False,
            },
        )
        self.assertEqual(self.load_yaml_mapping("{}", Path("empty.yaml")), {})

    def test_standard_safe_loader_string_key_normalization_is_preserved(self):
        self.assertEqual(
            self.load_yaml_mapping("=: value\n", Path("keys.yaml")), {"=": "value"}
        )

    def test_invalid_yaml_timestamp_values_include_filename(self):
        for text in ("when: 2026-02-30\n", "when: 2026-99-01\n"):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, "timestamp.yaml"):
                    self.load_yaml_mapping(text, Path("timestamp.yaml"))

    def test_empty_nonmapping_and_malformed_yaml_are_errors_with_filename(self):
        for text in (
            "", "# Only a comment\n", "null", "[]", "[one, two]", "42", "plain text",
            "tools: [view", "description: valid\n---\nother: document\n",
            "description: !!python/name:builtins.str ''",
        ):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, "broken.yaml"):
                    self.load_yaml_mapping(text, Path("broken.yaml"))

    def test_duplicate_keys_are_rejected_at_any_mapping_depth(self):
        for text in (
            "tools: [view]\ntools: []\n",
            "description: one\ndescription: two\n",
            "nested:\n  field: one\n  field: two\n",
            "tools: [view]\n? tools\n: []\n",
        ):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, "duplicate"):
                    self.load_yaml_mapping(text, Path("duplicate.yaml"))

    def test_mapping_keys_must_be_strings_at_every_depth(self):
        for text in (
            "1: value", "true: value", "null: value",
            "? [one, two]\n: value", "nested:\n  1: value\n",
        ):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, "keys.yaml"):
                    self.load_yaml_mapping(text, Path("keys.yaml"))

    def test_yaml_merge_keys_are_rejected_instead_of_overriding_permissions(self):
        for text in (
            "base: &base {tools: [view]}\n<<: *base\n",
            "base: &base {tools: [view]}\n<<: *base\ntools: ['*']\n",
            "base: &base {tools: [view]}\nprofile:\n  <<: *base\n",
            "one: &one {tools: [view]}\ntwo: &two {tools: []}\n<<: [*one, *two]\n",
        ):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, "merge"):
                    self.load_yaml_mapping(text, Path("merge.yaml"))


class AgentMetadataTest(HelperTestCase):
    def setUp(self):
        super().setUp()
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.source = self.root / "agents" / "reviewer.md"

    def _agent(self, **overrides):
        return markdown({"description": "Review changes.", "tools": ["view"], **overrides})

    def _profile(self, metadata):
        path = self.root / "copilot" / "agents" / "reviewer.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8")
        return path

    def test_representable_source_metadata_and_tool_order_are_preserved(self):
        fields = {
            "name": "Reviewer",
            "description": "First line.\nSecond line.\n",
            "tools": ["Bash", "Read", "Grep", "Glob", "Write", "Task", "repo-search/search"],
            "model": "gpt-5.4",
            "target": "copilot-cli",
            "user-invocable": False,
            "disable-model-invocation": True,
            "infer": False,
        }
        self.assertEqual(
            self.agent_metadata(self.root, self.source, markdown(fields)), fields
        )

    def test_comma_separated_source_tools_are_not_replaced_with_generic_fallback(self):
        result = self.agent_metadata(
            self.root, self.source,
            self._agent(tools="Bash, Read, Grep, Glob, Write, Task, repo-search/search"),
        )
        self.assertEqual(
            result["tools"], ["Bash", "Read", "Grep", "Glob", "Write", "Task", "repo-search/search"]
        )

    def test_documented_cli_names_and_compatible_aliases_are_accepted(self):
        tools = [
            "bash", "shell", "execute", "powershell", "view", "Read", "NotebookRead",
            "read_bash", "write_bash", "stop_bash", "list_bash",
            "read_powershell", "write_powershell", "stop_powershell", "list_powershell",
            "grep", "glob", "rg", "search", "edit", "create", "apply_patch",
            "Write", "MultiEdit", "NotebookEdit", "write", "task", "agent", "custom-agent",
            "runSubagent", "list_agents", "read_agent", "write_agent",
            "web", "web_fetch", "WebFetch", "WebSearch", "ask_user", "skill",
        ]
        self.assertEqual(
            self.agent_metadata(self.root, self.source, self._agent(tools=tools))["tools"],
            tools,
        )

    def test_explicit_mcp_identifiers_and_wildcards_are_preserved(self):
        for tools in (
            ["repo-search/search", "lesson-runtime/lesson_learned", "atlassian/getJiraIssue"],
            ["my.server/read_tool", "my.server/*"],
            ["*"],
            ["view", "*"],
        ):
            with self.subTest(tools=tools):
                self.assertEqual(
                    self.agent_metadata(self.root, self.source, self._agent(tools=tools))["tools"],
                    tools,
                )

    def test_empty_tools_list_grants_none_and_does_not_synthesize_model(self):
        self.assertEqual(
            self.agent_metadata(self.root, self.source, self._agent(tools=[])),
            {"description": "Review changes.", "tools": []},
        )

    def test_missing_tools_never_defaults_to_all_tools(self):
        with self.assertRaisesRegex(ValueError, "reviewer.md.*tools"):
            self.agent_metadata(self.root, self.source, markdown({"description": "Review."}))

    def test_invalid_tools_shapes_and_empty_string_items_are_rejected(self):
        for tools in (None, "", " ", False, 1, {}, [1], [None], [""], [" "], "Read,", ["Read,Glob"]):
            with self.subTest(tools=tools):
                with self.assertRaisesRegex(ValueError, "reviewer.md.*tool"):
                    self.agent_metadata(self.root, self.source, self._agent(tools=tools))

    def test_unknown_tools_and_claude_mcp_names_are_rejected_not_dropped(self):
        for tool in (
            "codebase", "fetch", "not-a-tool", "mcp__server__tool",
            "server", "server/", "/tool", "server/tool/extra",
            "*/tool", "server/**", "server/tool*", "server/(tool)",
            "shell(git:*)", "https://example.invalid/tool",
        ):
            with self.subTest(tool=tool):
                with self.assertRaisesRegex(ValueError, "reviewer.md.*tool"):
                    self.agent_metadata(self.root, self.source, self._agent(tools=["view", tool]))

    def test_description_is_required_and_must_be_a_nonempty_string(self):
        for description in (None, "", " ", 1, False, [], {}):
            with self.subTest(description=description):
                with self.assertRaisesRegex(ValueError, "reviewer.md.*description"):
                    self.agent_metadata(
                        self.root, self.source, self._agent(description=description)
                    )
        with self.assertRaisesRegex(ValueError, "reviewer.md.*description"):
            self.agent_metadata(self.root, self.source, markdown({"tools": []}))

    def test_absent_null_and_source_inherit_model_inherit_session(self):
        for text in (self._agent(), self._agent(model=None), self._agent(model="inherit")):
            with self.subTest(text=text):
                self.assertNotIn("model", self.agent_metadata(self.root, self.source, text))

    def test_explicit_copilot_model_ids_are_retained_verbatim(self):
        for model in ("claude-sonnet-4.6", "gpt-5.4", "gemini-3-pro-preview"):
            with self.subTest(model=model):
                self.assertEqual(
                    self.agent_metadata(self.root, self.source, self._agent(model=model))["model"],
                    model,
                )

    def test_claude_model_aliases_and_invalid_models_need_explicit_profile_decisions(self):
        for model in ("sonnet", "opus", "haiku", "Sonnet", "opusplan", "sonnet[1m]", "", " ", False, [], {}, "gpt-5.4 high"):
            with self.subTest(model=model):
                with self.assertRaisesRegex(ValueError, "reviewer.md.*model"):
                    self.agent_metadata(self.root, self.source, self._agent(model=model))

    def test_native_field_types_and_targets_are_checked(self):
        for field, value in (
            ("name", ""), ("name", 3),
            ("target", "vscode"), ("target", "claude-code"), ("target", None),
            ("user-invocable", "false"), ("disable-model-invocation", 0), ("infer", "yes"),
        ):
            with self.subTest(field=field, value=value):
                with self.assertRaisesRegex(ValueError, f"reviewer.md.*{field}"):
                    self.agent_metadata(self.root, self.source, self._agent(**{field: value}))
        for target in ("copilot-cli", "github-copilot"):
            self.assertEqual(
                self.agent_metadata(self.root, self.source, self._agent(target=target))["target"],
                target,
            )

    def test_unsupported_source_semantics_are_rejected_even_with_profile(self):
        self._profile({"tools": ["view"], "model": None})
        for field in (
            "permissionMode", "permissions", "allowed-tools", "disallowedTools", "hooks",
            "memory", "isolation", "skills", "background", "maxTurns", "mcpServers",
            "mcp-servers", "models", "modelPolicy", "reasoningEffort", "unknown",
        ):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, f"reviewer.md.*{field}"):
                    self.agent_metadata(self.root, self.source, self._agent(**{field: False}))

    def test_profile_explicitly_replaces_claude_tools_and_model_without_erasing_other_fields(self):
        self._profile({
            "tools": ["view", "repo-search/search"],
            "model": None,
            "target": "copilot-cli",
        })
        text = self._agent(
            name="Source name", tools="mcp__old__tool, Read", model="sonnet",
            **{"user-invocable": False},
        )
        self.assertEqual(
            self.agent_metadata(self.root, self.source, text),
            {
                "name": "Source name", "description": "Review changes.",
                "tools": ["view", "repo-search/search"], "target": "copilot-cli",
                "user-invocable": False,
            },
        )

    def test_profile_can_supply_description_or_explicit_model(self):
        self._profile({"description": "Native reviewer.", "tools": [], "model": "gpt-5.4"})
        self.assertEqual(
            self.agent_metadata(self.root, self.source, "Body without frontmatter.\n"),
            {"description": "Native reviewer.", "tools": [], "model": "gpt-5.4"},
        )

    def test_profile_requires_its_own_tools_and_model_not_source_fallbacks(self):
        for metadata, missing in (({"model": None}, "tools"), ({"tools": []}, "model")):
            with self.subTest(missing=missing):
                self._profile(metadata)
                with self.assertRaisesRegex(ValueError, f"reviewer.yaml.*{missing}"):
                    self.agent_metadata(
                        self.root, self.source, self._agent(model="gpt-5.4")
                    )

    def test_profile_metadata_is_validated_with_profile_filename(self):
        for extra in (
            {"tools": None}, {"tools": ["not-a-tool"]}, {"tools": ["mcp__old__tool"]},
            {"model": "inherit"}, {"model": "sonnet"}, {"model": []}, {"model": ""},
            {"description": ""}, {"infer": "false"}, {"target": "vscode"},
            {"mcp-servers": {}}, {"permissions": {}}, {"models": ["gpt-5.4"]},
        ):
            with self.subTest(extra=extra):
                self._profile({"tools": ["view"], "model": None, **extra})
                with self.assertRaisesRegex(ValueError, "reviewer.yaml"):
                    self.agent_metadata(self.root, self.source, self._agent())

    def test_profile_yaml_must_be_nonempty_mapping_without_duplicate_or_merge_keys(self):
        path = self._profile({"tools": ["view"], "model": None})
        for text in (
            "", "[]", "tools: [view", "tools: []\ntools: ['*']\nmodel: null\n",
            "tools: []\nmodel: null\nmodel: gpt-5.4\n",
            "base: &base {tools: []}\n<<: *base\nmodel: null\n",
            "tools: []\nmodel: null\n1: invalid\n",
        ):
            with self.subTest(text=text):
                path.write_text(text, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "reviewer.yaml"):
                    self.agent_metadata(self.root, self.source, self._agent())

    def test_malformed_source_frontmatter_is_rejected_even_when_profile_overrides_it(self):
        self._profile({"description": "Native reviewer.", "tools": [], "model": None})
        for text in (
            "---\ntools: [Read\n---\nBody\n",
            "---\ntools: [Read]\ntools: []\n---\nBody\n",
            "---\n[]\n---\nBody\n",
            "---\n\n---\nBody\n",
            "---\ntools: [Read]\n",
        ):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, "reviewer.md"):
                    self.agent_metadata(self.root, self.source, text)

    def test_profile_lookup_uses_source_stem_only(self):
        self._profile({"tools": [], "model": None})
        other = self.root / "agents" / "other.md"
        self.assertEqual(
            self.agent_metadata(self.root, other, self._agent())["tools"], ["view"]
        )

    def test_symlinked_profile_ancestors_and_files_are_rejected_even_if_dangling(self):
        for relative in ("copilot", "copilot/agents", "copilot/agents/reviewer.yaml"):
            for dangling in (False, True):
                with self.subTest(relative=relative, dangling=dangling):
                    root = self.root / f"case-{uuid.uuid4().hex}"
                    root.mkdir()
                    linked = root / relative
                    linked.parent.mkdir(parents=True, exist_ok=True)
                    target = root / "linked-target"
                    if not dangling:
                        if relative.endswith(".yaml"):
                            target.write_text("tools: []\nmodel: null\n", encoding="utf-8")
                        else:
                            target.mkdir()
                    linked.symlink_to(target.resolve(), target_is_directory=not relative.endswith(".yaml"))
                    with self.assertRaisesRegex(ValueError, "symlink"):
                        self.agent_metadata(root, root / "agents/reviewer.md", self._agent())

    def test_profile_directories_must_be_directories_and_profile_must_be_regular_file(self):
        for relative in ("copilot", "copilot/agents", "copilot/agents/reviewer.yaml"):
            with self.subTest(relative=relative):
                root = self.root / f"case-{uuid.uuid4().hex}"
                path = root / relative
                path.parent.mkdir(parents=True)
                if relative.endswith(".yaml"):
                    path.mkdir()
                else:
                    path.write_text("not a directory", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "copilot"):
                    self.agent_metadata(root, root / "agents/reviewer.md", self._agent())

    def test_non_utf8_profile_is_a_value_error_with_profile_filename(self):
        path = self._profile({"tools": [], "model": None})
        path.write_bytes(b"\xff\xfe")
        with self.assertRaisesRegex(ValueError, "reviewer.yaml"):
            self.agent_metadata(self.root, self.source, self._agent())


class RuleMetadataTest(HelperTestCase):
    source = Path("rules/nested/code-quality.md")

    def test_absent_scope_is_global_with_existing_default_description(self):
        for text in ("Body.\n", markdown({}), markdown({"description": "Use safe code."})):
            with self.subTest(text=text):
                result = self.rule_metadata(self.source, text)
                self.assertEqual(result["applyTo"], "**")
                self.assertEqual(
                    result["description"],
                    "Use safe code." if "description:" in text else "code-quality governance rules.",
                )

    def test_single_and_list_scopes_are_preserved_without_broadening(self):
        for paths, expected in (
            ("src/**/*.py", "src/**/*.py"),
            (["src/**/*.py", "tests/*.py"], "src/**/*.py,tests/*.py"),
            ([".github/*.yml", "README.md", "*", "**"], ".github/*.yml,README.md,*,**"),
        ):
            with self.subTest(paths=paths):
                self.assertEqual(
                    self.rule_metadata(
                        self.source, markdown({"paths": paths, "description": "Scoped.\nDetails.\n"})
                    ),
                    {"applyTo": expected, "description": "Scoped.\nDetails.\n"},
                )

    def test_brace_alternatives_expand_before_comma_joining(self):
        for paths, expected in (
            ("src/**/*.{ts,tsx}", "src/**/*.ts,src/**/*.tsx"),
            ("{src,tests}/**/*.{ts,tsx}", "src/**/*.ts,src/**/*.tsx,tests/**/*.ts,tests/**/*.tsx"),
            ("src/{ui,{api,lib}}/*.{ts,js}", "src/ui/*.ts,src/ui/*.js,src/api/*.ts,src/api/*.js,src/lib/*.ts,src/lib/*.js"),
            (["src/{a,b}/**", "docs/*.md"], "src/a/**,src/b/**,docs/*.md"),
            ("{src/client,src/server}/**", "src/client/**,src/server/**"),
        ):
            with self.subTest(paths=paths):
                self.assertEqual(
                    self.rule_metadata(self.source, markdown({"paths": paths}))["applyTo"],
                    expected,
                )

    def test_empty_or_nonstring_scopes_are_rejected_not_made_global(self):
        for paths in (None, "", " ", [], [""], ["src/**", None], ["src/**", ""], 1, False, {}):
            with self.subTest(paths=paths):
                with self.assertRaisesRegex(ValueError, "code-quality.md.*paths"):
                    self.rule_metadata(self.source, markdown({"paths": paths}))

    def test_nonrepresentable_and_escaping_globs_are_rejected(self):
        for pattern in (
            "!src/**", "/src/**", "../src/**", "src/../private/**", "./src/**",
            "C:/src/**", r"C:\src\**", "//server/share/**", "~/src/**",
            "src//**", "src/", "src/**.ts", "src/a**b.ts", "src/***/file",
            "src/?.ts", "src/[ab].ts", "src/@(a|b).ts", "src/!(a).ts",
            "src/*.ts,tests/*.ts", "src/*.ts\n", "src/*.ts\rtests/*",
            "src/{a,b", "src/a,b}", "src/{a}", "src/{a,}", "src/{,b}",
            "src/{a,,b}", "src/{a,{b,c}", "src/{a,b}}", "src/{1..3}/**",
            "src/{safe,../private}/**", "{/absolute,relative}/**",
            "src/{safe,{also-safe,../../private}}/**",
        ):
            with self.subTest(pattern=pattern):
                with self.assertRaisesRegex(ValueError, "code-quality.md.*paths"):
                    self.rule_metadata(self.source, markdown({"paths": pattern}))

    def test_brace_expansion_and_nesting_are_bounded(self):
        for pattern in ("src/" + "{a,b}" * 10, "src/" + "{a," * 40 + "b" + "}" * 40):
            with self.subTest(pattern=pattern):
                with self.assertRaisesRegex(ValueError, "code-quality.md.*paths"):
                    self.rule_metadata(self.source, markdown({"paths": pattern}))

    def test_unknown_semantic_rule_fields_are_rejected(self):
        for field in ("alwaysApply", "applyTo", "exclude", "globs", "model", "tools", "unknown"):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, f"code-quality.md.*{field}"):
                    self.rule_metadata(self.source, markdown({"paths": "src/**", field: True}))

    def test_rule_descriptions_must_be_nonempty_strings_when_present(self):
        for description in (None, "", " ", False, [], 4):
            with self.subTest(description=description):
                with self.assertRaisesRegex(ValueError, "code-quality.md.*description"):
                    self.rule_metadata(self.source, markdown({"description": description}))

    def test_invalid_frontmatter_never_falls_back_to_global_scope(self):
        for text in (
            "---\npaths: [src/**\n---\nBody\n",
            "---\npaths: src/**\npaths: tests/**\n---\nBody\n",
            "---\npaths: src/**\n",
            "---\n\n---\nBody\n",
            "---\n[]\n---\nBody\n",
            "--- \npaths: src/**\n---\nBody\n",
            "---\r\npaths: src/**\r\n---\r\nBody\n",
            "\ufeff---\npaths: src/**\n---\nBody\n",
        ):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, "code-quality.md"):
                    self.rule_metadata(self.source, text)


class RepositoryAgentProfilesTest(HelperTestCase):
    def test_four_real_profiles_are_explicit_and_preserve_source_descriptions(self):
        expected_builtins = {
            "pr-reviewer": {
                "bash", "view", "grep", "glob", "create", "edit", "apply_patch",
            },
            "pipeline-checker": {"bash", "view", "grep", "glob"},
            "code-review-depth": {"view", "glob"},
            "code-review-breadth": {"view", "glob"},
        }
        atlassian_aliases = {"plugin_atlassian_atlassian", "claude_ai_Atlassian_2"}
        for name, builtins in expected_builtins.items():
            with self.subTest(agent=name):
                source = ROOT / "agents" / f"{name}.md"
                profile = ROOT / "copilot" / "agents" / f"{name}.yaml"
                self.assertTrue(profile.is_file(), f"Missing explicit profile: {profile}")
                before = source.read_bytes()
                source_frontmatter, _ = self.split_frontmatter(before.decode("utf-8"))
                source_metadata = self.load_yaml_mapping(source_frontmatter[4:-4], source)
                profile_metadata = self.load_yaml_mapping(profile.read_text(encoding="utf-8"), profile)
                self.assertIn("model", profile_metadata)
                self.assertIsNone(profile_metadata["model"])
                metadata = self.agent_metadata(ROOT, source, before.decode("utf-8"))
                self.assertNotIn("model", metadata)
                self.assertEqual(metadata["description"], source_metadata["description"])
                self.assertEqual(metadata["name"], source_metadata["name"])
                self.assertEqual(metadata["target"], "copilot-cli")
                source_mcp_tools = set()
                for source_tool in source_metadata["tools"].split(","):
                    source_tool = source_tool.strip()
                    if source_tool.startswith("mcp__"):
                        _, server, operation = source_tool.split("__", 2)
                        server = "atlassian" if server in atlassian_aliases else server
                        source_mcp_tools.add(f"{server}/{operation}")
                tools = builtins | source_mcp_tools
                self.assertEqual(set(metadata["tools"]), tools)
                self.assertEqual(len(metadata["tools"]), len(tools))
                self.assertEqual(metadata["user-invocable"], name == "pr-reviewer")
                self.assertFalse(
                    any(
                        tool.split("/", 1)[1].lower().startswith((
                            "add", "apply", "complete", "create", "delete", "execute",
                            "post", "remove", "rollback", "send", "update", "write",
                        ))
                        for tool in metadata["tools"] if "/" in tool
                    ),
                    f"{name} must not gain external mutation capabilities",
                )
                self.assertEqual(source.read_bytes(), before)
                if name.startswith("code-review-"):
                    self.assertNotIn("firebase", source_metadata["tools"].lower())


if __name__ == "__main__":
    unittest.main()
