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


def _repeated_yaml_keys(node: Node | None, loader: yaml.SafeLoader) -> list[str]:
    """Return scalar keys whose loaded identities collide at any depth."""
    if isinstance(node, MappingNode):
        # A merge directive is not a key in the loaded mapping.
        scalar_keys = [
            key
            for key, _ in node.value
            if isinstance(key, ScalarNode) and key.tag != "tag:yaml.org,2002:merge"
        ]
        keys = [loader.construct_object(key) for key in scalar_keys]
        repeated = sorted(
            {
                key.value
                for key, loaded in zip(scalar_keys, keys, strict=True)
                if keys.count(loaded) > 1
            }
        )
        return repeated + [
            name
            for _, value in node.value
            for name in _repeated_yaml_keys(value, loader)
        ]
    if isinstance(node, SequenceNode):
        return [
            name for item in node.value for name in _repeated_yaml_keys(item, loader)
        ]
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
        loader = yaml.SafeLoader(text)
        try:
            repeated = []
            while loader.check_data():
                repeated.extend(_repeated_yaml_keys(loader.get_node(), loader))
        finally:
            loader.dispose()
        assert not repeated, repeated


@pytest.mark.parametrize(
    ("text", "repeated"),
    [
        ("name: first\nname: second\n", "name"),
        ("1: first\n0x1: second\n", "0x1"),
        ("1: first\n01: second\n", "01"),
        ("1: first\n1.0: second\n", "1.0"),
        ("true: first\n1: second\n", "1"),
        ("false: first\n0: second\n", "0"),
        ("true: first\nyes: second\n", "yes"),
        ("null: first\n~: second\n", "~"),
        ("nested:\n  - 1: first\n    0x1: second\n", "0x1"),
        ("name: first\n---\n1: first\n0x1: second\n", "0x1"),
    ],
    ids=[
        "same-spelling",
        "hexadecimal",
        "octal",
        "float-integer",
        "true-integer",
        "false-integer",
        "boolean-spellings",
        "null-spellings",
        "nested-sequence",
        "later-document",
    ],
)
def test_yaml_template_rejects_keys_with_equal_loaded_values(
    tmp_path: Path, text: str, repeated: str
) -> None:
    template = tmp_path / "example.yaml.template"
    template.write_text(text, encoding="utf-8")

    with pytest.raises(AssertionError, match=repeated):
        test_structured_template_parses_without_repeated_keys(template)


@pytest.mark.parametrize(
    "text",
    [
        "1: numeric\n'1': string\n",
        "true: boolean\n'true': string\n",
        "1.0: numeric\n'1.0': string\n",
        "null: empty\n'null': string\n",
        "1: first\n2: second\n",
        "left:\n  name: first\nright:\n  name: second\n",
        "name: first\n---\nname: second\n",
        "",
        "---\n---\n",
        "base: &base {value: default}\ncopy: {<<: *base, value: override}\n",
    ],
    ids=[
        "integer-string",
        "boolean-string",
        "float-string",
        "null-string",
        "distinct-numbers",
        "separate-mappings",
        "separate-documents",
        "empty-stream",
        "empty-documents",
        "merge-override",
    ],
)
def test_yaml_template_accepts_distinct_loaded_keys(tmp_path: Path, text: str) -> None:
    template = tmp_path / "example.yml.template"
    template.write_text(text, encoding="utf-8")

    test_structured_template_parses_without_repeated_keys(template)


@pytest.mark.parametrize(
    "text",
    [
        "name: [unterminated\n",
        "? [unhashable, key]\n: value\n",
        "key: !unknown value\n",
    ],
    ids=["invalid-syntax", "unhashable-key", "unknown-tag"],
)
def test_yaml_template_preserves_explicit_loader_errors(
    tmp_path: Path, text: str
) -> None:
    template = tmp_path / "invalid.yaml.template"
    template.write_text(text, encoding="utf-8")

    with pytest.raises(yaml.YAMLError):
        test_structured_template_parses_without_repeated_keys(template)
