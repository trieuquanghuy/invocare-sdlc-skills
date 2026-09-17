"""Shared frontmatter splitting and strict, safe YAML mapping loading."""

from pathlib import Path

import yaml


def split_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---\n"):
        return "", text
    end = text.find("\n---\n", 4)
    if end < 0:
        return "", text
    return text[: end + 5], text[end + 5 :]


class _MappingLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        if not isinstance(node, yaml.nodes.MappingNode):
            raise yaml.constructor.ConstructorError(
                None, None, "expected a YAML mapping", node.start_mark
            )
        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                raise yaml.constructor.ConstructorError(
                    None, None, "YAML merge keys are not supported", key_node.start_mark
                )
        mapping = super().construct_mapping(node, deep=deep)
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise yaml.constructor.ConstructorError(
                    None, None, "YAML mapping keys must be strings", key_node.start_mark
                )
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate YAML key: {key}", key_node.start_mark
                )
            seen.add(key)
        return mapping


def load_yaml_mapping(text: str, path: Path) -> dict[str, object]:
    """Load raw YAML, rejecting implicit overrides and non-mapping documents."""
    try:
        metadata = yaml.load(text, Loader=_MappingLoader)
    except (yaml.YAMLError, ValueError, OverflowError) as error:
        raise ValueError(f"{path}: invalid YAML: {error}") from error
    if not isinstance(metadata, dict):
        raise ValueError(f"{path}: YAML document must be a mapping, not empty or scalar")
    return metadata
