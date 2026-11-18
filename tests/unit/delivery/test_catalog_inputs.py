"""Reject malformed catalog fields at public, loader-backed boundaries.

Error contract: DocumentError (not KeyError/TypeError/raw ValueError),
with the offending field in the diagnostic. Workflow descriptions are optional;
action input descriptions and workflow input types are required. ADO parameters
require names and types, not descriptions. Catalog loading preserves scalar types
without resolving the GitHub ``on`` key as a YAML 1.1 boolean.
"""

from __future__ import annotations

from copy import deepcopy
from textwrap import dedent, indent
from typing import TYPE_CHECKING

import pytest

from delivery_tools.catalog import (
    COMPOSITIONS,
    ROOT,
    WORKFLOW_FILES,
    build,
    is_source_file,
    parameters,
    render,
)
from delivery_tools.documents import DocumentError, mapping, parse_yaml, read_json

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.unit

_WORKFLOW = "delivery-python-ci.yml"
_ACTION = "actions/python-check/action.yml"


def _write_github_inputs(roots: tuple[Path, Path], owner: str, inputs: str) -> None:
    root, workflows = roots
    if owner == "workflow":
        path = workflows / _WORKFLOW
        text = (
            "on:\n  workflow_call:\n    inputs:\n"
            + indent(dedent(inputs).strip(), "      ")
            + "\npermissions:\n  contents: read\njobs: {}\n"
        )
    else:
        path = root / _ACTION
        text = (
            "name: Synthetic action\ndescription: Synthetic action.\ninputs:\n"
            + indent(dedent(inputs).strip(), "  ")
            + "\nruns:\n  using: composite\n  steps: []\n"
        )
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def catalog_roots(tmp_path: Path) -> tuple[Path, Path]:
    """Use the smallest source inventory accepted by build, not real package copies."""
    root = tmp_path / "package"
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    for name in WORKFLOW_FILES:
        (workflows / name).write_text(
            "on:\n  workflow_call: {}\npermissions:\n  contents: read\njobs: {}\n",
            encoding="utf-8",
        )
    (root / _ACTION).parent.mkdir(parents=True)
    roots = (root, workflows)
    _write_github_inputs(
        roots, "action", "pin:\n  description: Version pin.\n  default: stable\n"
    )
    required = ("README.md", "REFERENCE.md", "bicep/main.bicep", "terraform/main.tf")
    for composition in COMPOSITIONS:
        for name in required:
            path = root / composition / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
    return roots


def _github_inputs(catalog: dict[str, object], owner: str) -> dict[str, object]:
    group, name = (
        ("github", "delivery-python-ci")
        if owner == "workflow"
        else ("githubActions", "python-check")
    )
    return mapping(mapping(mapping(catalog[group])[name])["inputs"])


@pytest.mark.parametrize("owner", ["workflow", "action"])
@pytest.mark.parametrize(
    ("inputs", "field"),
    [
        pytest.param("[]", "mapping", id="inputs-list"),
        pytest.param("pin: []", "mapping", id="input-list"),
        pytest.param("pin: scalar", "mapping", id="input-scalar"),
        pytest.param(
            "pin: {type: string, description: []}",
            "description",
            id="description-list",
        ),
        pytest.param(
            "pin: {type: string, description: {text: Pin}}",
            "description",
            id="description-mapping",
        ),
        pytest.param(
            "pin: {type: string, description: Pin, required: maybe}",
            "required",
            id="required-invalid-token",
        ),
        pytest.param(
            "pin: {type: string, description: Pin, required: 1}",
            "required",
            id="required-number",
        ),
        pytest.param(
            "pin: {type: string, description: Pin, required: []}",
            "required",
            id="required-list",
        ),
        pytest.param(
            "pin: {type: string, description: Pin, required: {value: true}}",
            "required",
            id="required-mapping",
        ),
        pytest.param(
            "pin: {type: string, description: Pin, required: null}",
            "required",
            id="required-null-token",
        ),
        pytest.param(
            "pin: {type: string, description: Pin, default: []}",
            "default",
            id="string-default-list",
        ),
        pytest.param(
            "pin: {type: string, description: Pin, default: {value: pin}}",
            "default",
            id="string-default-mapping",
        ),
        pytest.param(
            "'': {type: string, description: Pin}", "name", id="empty-input-name"
        ),
    ],
)
def test_catalog_rejects_invalid_github_input_fields(
    catalog_roots: tuple[Path, Path], owner: str, inputs: str, field: str
) -> None:
    if owner == "action":
        inputs = inputs.replace("type: string, ", "")
    _write_github_inputs(catalog_roots, owner, inputs)
    root, workflows = catalog_roots
    with pytest.raises(DocumentError, match=rf"(?i){field}"):
        build(root, workflow_root=workflows)


@pytest.mark.parametrize(
    ("definition", "field"),
    [
        pytest.param("{description: Pin}", "type", id="missing-type"),
        pytest.param("{type: ''}", "type", id="empty-type"),
        pytest.param("{type: []}", "type", id="type-list"),
        pytest.param("{type: {name: string}}", "type", id="type-mapping"),
        pytest.param("{type: true}", "type", id="type-boolean-token"),
        pytest.param("{type: 3}", "type", id="type-number-token"),
        pytest.param("{type: null}", "type", id="type-null-token"),
        pytest.param("{type: object}", "type", id="unsupported-type"),
        pytest.param(
            "{type: boolean, default: maybe}", "default", id="boolean-default-token"
        ),
        pytest.param(
            "{type: boolean, default: 1}", "default", id="boolean-default-number"
        ),
        pytest.param(
            "{type: boolean, default: []}", "default", id="boolean-default-list"
        ),
        pytest.param(
            "{type: number, default: nope}", "default", id="number-default-text"
        ),
        pytest.param(
            "{type: number, default: 1.2.3}", "default", id="number-default-malformed"
        ),
        pytest.param(
            "{type: number, default: true}", "default", id="number-default-boolean"
        ),
        pytest.param(
            "{type: number, default: []}", "default", id="number-default-list"
        ),
        pytest.param(
            "{type: number, default: 1.0e999}", "default", id="number-default-infinite"
        ),
        pytest.param(
            "{type: number, default: NaN}", "default", id="number-default-nan"
        ),
    ],
)
def test_catalog_rejects_invalid_workflow_input_types_and_defaults(
    catalog_roots: tuple[Path, Path], definition: str, field: str
) -> None:
    _write_github_inputs(catalog_roots, "workflow", f"pin: {definition}")
    root, workflows = catalog_roots
    with pytest.raises(DocumentError, match=rf"(?i){field}"):
        build(root, workflow_root=workflows)


def test_catalog_action_input_requires_description(
    catalog_roots: tuple[Path, Path],
) -> None:
    _write_github_inputs(catalog_roots, "action", "pin: {default: stable}")
    root, workflows = catalog_roots
    with pytest.raises(DocumentError, match=r"(?i)description"):
        build(root, workflow_root=workflows)


@pytest.mark.parametrize("owner", ["workflow", "action"])
def test_catalog_rejects_duplicate_input_names_before_overwriting(
    catalog_roots: tuple[Path, Path], owner: str
) -> None:
    kind = "type: string, " if owner == "workflow" else ""
    _write_github_inputs(
        catalog_roots,
        owner,
        f"pin: {{{kind}description: First}}\npin: {{{kind}description: Second}}\n",
    )
    root, workflows = catalog_roots
    with pytest.raises(DocumentError, match=r"(?i)duplicate"):
        build(root, workflow_root=workflows)


@pytest.mark.parametrize(
    ("definition", "expected"),
    [
        pytest.param(
            "{type: string}",
            {"type": "string", "required": False, "description": ""},
            id="optional-description-and-default",
        ),
        pytest.param(
            "{type: string, description: Pin, required: true, default: ''}",
            {"type": "string", "required": True, "description": "Pin", "default": ""},
            id="empty-string",
        ),
        pytest.param(
            "{type: string, default: 'false'}",
            {
                "type": "string",
                "required": False,
                "description": "",
                "default": "false",
            },
            id="string-is-not-boolean",
        ),
        pytest.param(
            "{type: boolean, required: false, default: false}",
            {"type": "boolean", "required": False, "description": "", "default": False},
            id="false",
        ),
        pytest.param(
            "{type: boolean, required: true, default: true}",
            {"type": "boolean", "required": True, "description": "", "default": True},
            id="true",
        ),
        pytest.param(
            "{type: number, default: 0}",
            {"type": "number", "required": False, "description": "", "default": 0},
            id="zero",
        ),
        pytest.param(
            "{type: number, default: -1}",
            {"type": "number", "required": False, "description": "", "default": -1},
            id="negative",
        ),
        pytest.param(
            "{type: number, default: 1.5}",
            {"type": "number", "required": False, "description": "", "default": 1.5},
            id="fraction",
        ),
    ],
)
def test_catalog_preserves_valid_workflow_defaults_and_scalar_types(
    catalog_roots: tuple[Path, Path],
    definition: str,
    expected: dict[str, object],
) -> None:
    _write_github_inputs(catalog_roots, "workflow", f"pin: {definition}")
    root, workflows = catalog_roots
    actual = mapping(
        _github_inputs(build(root, workflow_root=workflows), "workflow")["pin"]
    )
    assert actual == expected
    if "default" in expected:
        assert type(actual["default"]) is type(expected["default"]), (
            "Numeric zero and one must not become booleans"
        )


def test_catalog_action_inputs_are_strings_without_a_type_field(
    catalog_roots: tuple[Path, Path],
) -> None:
    _write_github_inputs(
        catalog_roots,
        "action",
        "pin: {description: Pin, required: true, default: 'false'}\n"
        "empty: {description: Optional pin, required: false, default: ''}\n",
    )
    root, workflows = catalog_roots
    assert _github_inputs(build(root, workflow_root=workflows), "action") == {
        "pin": {
            "type": "string",
            "required": True,
            "description": "Pin",
            "default": "false",
        },
        "empty": {
            "type": "string",
            "required": False,
            "description": "Optional pin",
            "default": "",
        },
    }


@pytest.mark.parametrize(
    ("item", "field"),
    [
        pytest.param("{type: string}", "name", id="missing-name"),
        pytest.param("{name: pin}", "type", id="missing-type"),
        pytest.param("{name: '', type: string}", "name", id="empty-name"),
        pytest.param("{name: null, type: string}", "name", id="null-name"),
        pytest.param("{name: true, type: string}", "name", id="boolean-name"),
        pytest.param("{name: 7, type: string}", "name", id="numeric-name"),
        pytest.param("{name: [], type: string}", "name", id="list-name"),
        pytest.param("{name: {}, type: string}", "name", id="mapping-name"),
        pytest.param("{name: pin, type: null}", "type", id="null-type"),
        pytest.param("{name: pin, type: false}", "type", id="boolean-type"),
        pytest.param("{name: pin, type: 7}", "type", id="numeric-type"),
        pytest.param("{name: pin, type: []}", "type", id="list-type"),
        pytest.param("{name: pin, type: {}}", "type", id="mapping-type"),
        pytest.param("{name: pin, type: ''}", "type", id="empty-type"),
        pytest.param("{name: pin, type: imaginary}", "type", id="unknown-type"),
        pytest.param(
            "{name: pin, type: string, default: 7}", "default", id="string-number"
        ),
        pytest.param(
            "{name: pin, type: string, default: false}", "default", id="string-boolean"
        ),
        pytest.param(
            "{name: pin, type: string, default: []}", "default", id="string-list"
        ),
        pytest.param(
            "{name: pin, type: string, default: {}}", "default", id="string-mapping"
        ),
        pytest.param(
            "{name: pin, type: boolean, default: maybe}", "default", id="boolean-text"
        ),
        pytest.param(
            "{name: pin, type: boolean, default: 1}", "default", id="boolean-number"
        ),
        pytest.param(
            "{name: pin, type: boolean, default: null}", "default", id="boolean-null"
        ),
        pytest.param(
            "{name: pin, type: boolean, default: []}", "default", id="boolean-list"
        ),
        pytest.param(
            "{name: pin, type: number, default: false}", "default", id="number-boolean"
        ),
        pytest.param(
            "{name: pin, type: number, default: nope}", "default", id="number-text"
        ),
        pytest.param(
            "{name: pin, type: number, default: 1.2.3}",
            "default",
            id="number-malformed",
        ),
        pytest.param(
            "{name: pin, type: number, default: .inf}", "default", id="number-infinity"
        ),
        pytest.param(
            "{name: pin, type: number, default: .nan}", "default", id="number-nan"
        ),
        pytest.param(
            "{name: pin, type: number, default: {}}", "default", id="number-mapping"
        ),
        pytest.param(
            "{name: pin, type: stepList, default: {}}",
            "default",
            id="step-list-mapping",
        ),
        pytest.param(
            "{name: pin, type: string, values: stable}", "values", id="values-scalar"
        ),
        pytest.param(
            "{name: pin, type: string, values: {stable: true}}",
            "values",
            id="values-mapping",
        ),
    ],
)
def test_catalog_parameters_reject_invalid_fields(item: str, field: str) -> None:
    document = parse_yaml(f"parameters:\n  - {item}\n")
    with pytest.raises(DocumentError, match=rf"(?i){field}"):
        parameters(document)


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("parameters: {}", id="mapping"),
        pytest.param("parameters: string", id="scalar"),
        pytest.param("parameters: null", id="null"),
    ],
)
def test_catalog_parameters_require_a_list(text: str) -> None:
    with pytest.raises(DocumentError, match=r"(?i)parameters.*list"):
        parameters(parse_yaml(text))


@pytest.mark.parametrize("item", ["[]", "false", "3", "null"])
def test_catalog_parameter_items_require_mappings(item: str) -> None:
    with pytest.raises(DocumentError, match=r"(?i)mapping"):
        parameters(parse_yaml(f"parameters:\n  - {item}\n"))


def test_catalog_parameters_reject_duplicate_names_from_loader() -> None:
    document = parse_yaml(
        "parameters:\n  - {name: pin, type: string}\n  - {name: pin, type: number}\n"
    )
    with pytest.raises(DocumentError, match=r"(?i)duplicate.*pin"):
        parameters(document)


def test_catalog_parameters_preserve_valid_types_defaults_and_source() -> None:
    document = parse_yaml(
        dedent("""\
        parameters:
          - {name: pin, type: string}
          - {name: empty, type: string, default: ''}
          - {name: enabled, type: boolean, default: true}
          - {name: disabled, type: boolean, default: false}
          - {name: zero, type: number, default: 0}
          - {name: negative, type: number, default: -1}
          - {name: fraction, type: number, default: 1.5}
          - {name: mode, type: string, default: stable, values: [stable, preview]}
          - {name: settings, type: object, default: {enabled: true}}
          - {name: items, type: object, default: []}
          - {name: steps, type: stepList, default: []}
        """)
    )
    before = deepcopy(document)
    actual = parameters(document)
    assert actual == {
        "pin": {"type": "string", "required": True},
        "empty": {"type": "string", "required": False, "default": ""},
        "enabled": {"type": "boolean", "required": False, "default": True},
        "disabled": {"type": "boolean", "required": False, "default": False},
        "zero": {"type": "number", "required": False, "default": 0},
        "negative": {"type": "number", "required": False, "default": -1},
        "fraction": {"type": "number", "required": False, "default": 1.5},
        "mode": {
            "type": "string",
            "required": False,
            "default": "stable",
            "values": ["stable", "preview"],
        },
        "settings": {"type": "object", "required": False, "default": {"enabled": True}},
        "items": {"type": "object", "required": False, "default": []},
        "steps": {"type": "stepList", "required": False, "default": []},
    }
    assert actual["enabled"]["default"] is True
    assert actual["disabled"]["default"] is False
    assert type(actual["zero"]["default"]) is int
    assert type(actual["fraction"]["default"]) is float
    assert document == before, "Catalog extraction must not mutate decoded source"
    assert parameters({}) == {}
    assert parameters(parse_yaml("parameters: []")) == {}


def test_catalog_build_rejects_invalid_ado_instead_of_returning_partial_catalog(
    catalog_roots: tuple[Path, Path],
) -> None:
    root, workflows = catalog_roots
    target = root / "azure-devops/steps/synthetic.yml"
    target.parent.mkdir(parents=True)
    target.write_text(
        "parameters:\n  - {name: pin, type: boolean, default: maybe}\n",
        encoding="utf-8",
    )
    with pytest.raises(DocumentError, match=r"(?i)default"):
        build(root, workflow_root=workflows)


def test_catalog_valid_source_inventory_and_render_remain_unchanged() -> None:
    workflows = ROOT.parents[1] / ".github/workflows"
    checked_in = ROOT / "catalog.json"
    assert build(ROOT, workflow_root=workflows) == read_json(checked_in)
    assert render(ROOT, workflow_root=workflows) == checked_in.read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize("owner", ["workflow", "action"])
@pytest.mark.parametrize(
    ("fields", "field"),
    [
        ("required: 'true'", "required"),
        ("required: yes", "required"),
        ("description: false", "description"),
        ("description: null", "description"),
        ("default: false", "default"),
        ("default: 12", "default"),
        ("default: null", "default"),
        ("default: stable, default: other", "duplicate"),
        ("required: true, required: false", "duplicate"),
    ],
)
def test_catalog_rejects_coerced_scalars_and_duplicate_fields(
    catalog_roots: tuple[Path, Path], owner: str, fields: str, field: str
) -> None:
    prefix = "type: string, " if owner == "workflow" else ""
    if "description:" not in fields:
        prefix += "description: Pin, "
    _write_github_inputs(catalog_roots, owner, f"pin: {{{prefix}{fields}}}")
    root, workflows = catalog_roots
    with pytest.raises(DocumentError, match=rf"(?i){field}"):
        build(root, workflow_root=workflows)


@pytest.mark.parametrize(
    "definition",
    [
        "{type: boolean, default: 'false'}",
        "{type: boolean, default: off}",
        "{type: number, default: '1.5'}",
        "{type: number, default: .inf}",
        "{type: number, default: .nan}",
    ],
)
def test_catalog_workflow_defaults_are_not_coerced(
    catalog_roots: tuple[Path, Path], definition: str
) -> None:
    _write_github_inputs(catalog_roots, "workflow", f"pin: {definition}")
    root, workflows = catalog_roots
    with pytest.raises(DocumentError, match="default"):
        build(root, workflow_root=workflows)


@pytest.mark.parametrize(
    ("text", "field"),
    [
        ("jobs: {}", "on"),
        ("on: {}", "workflow_call"),
        ("on: {workflow_call: {}}", "permissions"),
        ("on: {workflow_call: {}}\npermissions: {contents: .nan}", "permissions"),
        ("on: {workflow_call: {}}\npermissions: {contents: 2026-11-06}", "permissions"),
        ("on: {workflow_call: {secrets: []}}", "secrets"),
        ("on: {workflow_call: {secrets: {token: {required: 'false'}}}}", "required"),
        ("on: {workflow_call: {secrets: {token: {description: []}}}}", "description"),
        ("on: {workflow_call: {secrets: {'': {}}}}", "name"),
        (
            "on: {workflow_call: {inputs: {pin: {type: boolean, default: !!bool maybe}}}}",
            "default",
        ),
        ("on: [", "YAML"),
        ("on: !!python/object:x {}", "YAML"),
        ("on: &on {workflow_call: *on}", "aliases"),
    ],
)
def test_catalog_invalid_workflow_documents_fail_closed(
    catalog_roots: tuple[Path, Path], text: str, field: str
) -> None:
    root, workflows = catalog_roots
    (workflows / _WORKFLOW).write_text(text, encoding="utf-8")
    with pytest.raises(DocumentError, match=rf"(?i){field}"):
        build(root, workflow_root=workflows)
    with pytest.raises(DocumentError, match=rf"(?i){field}"):
        render(root, workflow_root=workflows)


@pytest.mark.parametrize(
    ("item", "field"),
    [
        ("{name: pin, type: boolean, default: 'true'}", "default"),
        ("{name: pin, type: number, default: '1'}", "default"),
        ("{name: pin, type: string, values: [stable, 1]}", "values"),
        ("{name: pin, type: boolean, values: [false, 1]}", "values"),
        ("{name: pin, type: number, values: [.inf]}", "values"),
        ("{name: pin, type: stepList, default: [false]}", "default"),
        ("{name: pin, type: job, default: []}", "default"),
        ("{name: pin, type: object, default: {nested: [.nan]}}", "default"),
        ("{name: pin, type: object, default: 2026-11-06}", "default"),
        ("{name: pin, type: string, type: number}", "duplicate"),
    ],
)
def test_catalog_parameter_nested_values_are_typed(item: str, field: str) -> None:
    with pytest.raises(DocumentError, match=rf"(?i){field}"):
        parameters(parse_yaml(f"parameters:\n  - {item}\n"))


def test_catalog_preserves_on_string_and_typed_secret(
    catalog_roots: tuple[Path, Path],
) -> None:
    root, workflows = catalog_roots
    (workflows / _WORKFLOW).write_text(
        "on:\n  workflow_call:\n"
        "    inputs:\n      switch: {type: string, default: on}\n"
        "    secrets:\n      token: {required: true}\n"
        "permissions: {contents: read}\n",
        encoding="utf-8",
    )
    contract = mapping(
        mapping(build(root, workflow_root=workflows)["github"])["delivery-python-ci"]
    )
    assert mapping(mapping(contract["inputs"])["switch"])["default"] == "on"
    assert contract["secrets"] == {"token": {"required": True, "description": ""}}


@pytest.mark.parametrize("kind", ["step", "job", "deployment", "stage"])
@pytest.mark.parametrize("suffix", ["", "List"])
def test_catalog_preserves_structured_template_parameter_shapes(
    kind: str, suffix: str
) -> None:
    default: object = (
        [{"template": "check.yml"}] if suffix else {"template": "check.yml"}
    )
    assert parameters(
        {"parameters": [{"name": "hook", "type": kind + suffix, "default": default}]}
    ) == {"hook": {"type": kind + suffix, "required": False, "default": default}}


@pytest.mark.parametrize("default", [None, "value", True, 1, 1.5, {}, []])
def test_catalog_object_parameters_accept_json_compatible_yaml(default: object) -> None:
    assert (
        parameters(
            {"parameters": [{"name": "data", "type": "object", "default": default}]}
        )["data"]["default"]
        == default
    )


def test_catalog_parameters_reject_cyclic_decoded_defaults() -> None:
    default: list[object] = []
    default.append(default)
    with pytest.raises(DocumentError, match=r"default.*nested"):
        parameters(
            {"parameters": [{"name": "data", "type": "object", "default": default}]}
        )


def test_catalog_accepts_native_empty_workflow_call(
    catalog_roots: tuple[Path, Path],
) -> None:
    root, workflows = catalog_roots
    (workflows / _WORKFLOW).write_text(
        "on:\n  workflow_call:\npermissions: {contents: read}\n", encoding="utf-8"
    )
    workflow = mapping(
        mapping(build(root, workflow_root=workflows)["github"])["delivery-python-ci"]
    )
    assert workflow["inputs"] == {}
    assert workflow["secrets"] == {}


def test_catalog_projects_the_broadest_job_grant_for_callers(
    catalog_roots: tuple[Path, Path],
) -> None:
    root, workflows = catalog_roots
    (workflows / _WORKFLOW).write_text(
        "on:\n  workflow_call:\npermissions: {contents: read}\njobs:\n"
        "  a: {permissions: {contents: read, actions: read}}\n"
        "  b: {permissions: {contents: none, id-token: write}}\n"
        "  c: {runs-on: ubuntu-24.04}\n",
        encoding="utf-8",
    )
    workflow = mapping(
        mapping(build(root, workflow_root=workflows)["github"])["delivery-python-ci"]
    )
    assert workflow["permissions"] == {
        "actions": "read",
        "contents": "read",
        "id-token": "write",
    }


@pytest.mark.parametrize(
    ("jobs", "field"),
    [
        ("jobs: []", "jobs"),
        ("jobs: {a: []}", "jobs.a"),
        ("jobs: {a: {permissions: read-all}}", "jobs.a.permissions"),
        ("jobs: {a: {permissions: {contents: admin}}}", "permissions.contents"),
    ],
)
def test_catalog_rejects_unreviewable_job_permissions(
    catalog_roots: tuple[Path, Path], jobs: str, field: str
) -> None:
    root, workflows = catalog_roots
    (workflows / _WORKFLOW).write_text(
        f"on:\n  workflow_call:\npermissions: {{contents: read}}\n{jobs}\n",
        encoding="utf-8",
    )
    with pytest.raises(DocumentError, match=field):
        build(root, workflow_root=workflows)


def test_inventory_ignores_local_terraform_working_output(tmp_path: Path) -> None:
    """A local ``terraform init`` inside a module must not change the inventory."""
    module = tmp_path / "infra" / "x" / "terraform"
    providers = module / ".terraform" / "providers"
    providers.mkdir(parents=True)
    (module / "main.tf").write_text("", encoding="utf-8")
    (module / ".terraform.lock.hcl").write_text("", encoding="utf-8")
    (providers / "azapi.exe").write_text("", encoding="utf-8")

    sources = [
        path.relative_to(tmp_path).as_posix()
        for path in sorted(tmp_path.rglob("*"))
        if is_source_file(path, tmp_path)
    ]

    assert sources == ["infra/x/terraform/main.tf"]
