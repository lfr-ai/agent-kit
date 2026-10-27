"""Every shipped YAML, JSON and TOML template is well formed and unambiguous."""

import json
from pathlib import Path
import tomllib

import pytest
import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

_ROOT = Path(__file__).resolve().parents[3]
_KINDS = frozenset({"yaml", "yml", "json", "toml"})
_TEMPLATES = sorted(
    path
    for pattern in (".apm/**/*.template", "packages/*/.apm/**/*.template")
    for path in _ROOT.glob(pattern)
    if path.name.removesuffix(".template").rsplit(".", 1)[-1] in _KINDS
)


def _repeated_yaml_keys(node: Node | None) -> list[str]:
    """Return scalar mapping keys that appear more than once at any depth."""
    if isinstance(node, MappingNode):
        keys = [key.value for key, _ in node.value if isinstance(key, ScalarNode)]
        repeated = sorted({key for key in keys if keys.count(key) > 1})
        return repeated + [
            name for _, value in node.value for name in _repeated_yaml_keys(value)
        ]
    if isinstance(node, SequenceNode):
        return [name for item in node.value for name in _repeated_yaml_keys(item)]
    return []


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    keys = [key for key, _ in pairs]
    assert len(keys) == len(set(keys)), f"repeated JSON keys: {keys}"
    return dict(pairs)


def test_structured_templates_are_discovered() -> None:
    assert _TEMPLATES


@pytest.mark.parametrize(
    "template",
    _TEMPLATES,
    ids=[path.relative_to(_ROOT).as_posix() for path in _TEMPLATES],
)
def test_structured_template_parses_without_repeated_keys(template: Path) -> None:
    """A copied template must load in its consumer's tool exactly as written."""
    text = template.read_text(encoding="utf-8")
    kind = template.name.removesuffix(".template").rsplit(".", 1)[-1]

    if kind == "json":
        json.loads(text, object_pairs_hook=_unique_pairs)
    elif kind == "toml":
        tomllib.loads(text)
    else:
        list(yaml.safe_load_all(text))
        repeated = [
            name
            for document in yaml.compose_all(text, Loader=yaml.SafeLoader)
            for name in _repeated_yaml_keys(document)
        ]
        assert not repeated, repeated
