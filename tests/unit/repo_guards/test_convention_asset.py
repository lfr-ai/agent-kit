"""The bundled convention checker is exercised as installed source, not a copied guard."""

from pathlib import Path
import runpy
import shutil
import subprocess
import sys
from textwrap import dedent

import pytest

_PATH = (
    Path(__file__).parents[3]
    / "packages/backend/.apm/skills/kit-python-service/assets/check_python.py"
)


@pytest.mark.parametrize(
    "text",
    [
        "from typing import Any\n",
        "from logging import getLogger\n",
        "def run(x: 'Thing') -> None: pass\n",
        "class Thing:\n def __init__(self): pass\n",
        "from dataclasses import dataclass\n@dataclass\nclass Thing: pass\n",
        f'def run() -> None:\n    """Run {chr(96)}name{chr(96)}."""\n',
        'def run() -> None:\n    """Run \'name\'."""\n',
        'def run() -> None:\n    """Run \'an exact phrase\'."""\n',
        f'"""Module {chr(96) * 2}name."""\n',
        f'"""Module {chr(96) * 3}name{chr(96) * 3}."""\n',
    ],
)
def test_convention_asset_rejects_the_known_violation(text: str) -> None:
    """Original convention guarantees remain executable after extraction."""
    namespace = runpy.run_path(str(_PATH))
    assert namespace["violations"](text, "synthetic.py")


def test_convention_asset_accepts_double_backtick_docstring_code() -> None:
    """Double-backtick inline literals and backticks outside docs stay valid."""
    namespace = runpy.run_path(str(_PATH))
    source = (
        f'_FENCE = "{chr(96) * 3}"\n\n'
        f'def run() -> None:\n    """Run {chr(96) * 2}name{chr(96) * 2}."""\n'
    )
    assert namespace["violations"](source, "synthetic.py") == []


def test_convention_asset_can_select_docstring_rule(tmp_path: Path) -> None:
    """The docstring-only gate can scan assets without applying unrelated rules."""
    source = tmp_path / "asset.py"
    source.write_text(
        'from typing import Any\n\ndef run() -> None:\n    """Run ``name``."""\n',
        encoding="utf-8",
    )
    namespace = runpy.run_path(str(_PATH))

    assert namespace["main"](["--only", "docstring-backtick", str(source)]) == 0


def test_convention_asset_accepts_concrete_keyword_only_records() -> None:
    """Valid source is not rejected merely because it uses dataclasses."""
    namespace = runpy.run_path(str(_PATH))
    assert (
        namespace["violations"](
            "from dataclasses import dataclass\n"
            "@dataclass(frozen=True, kw_only=True, slots=True)\nclass Value: count: int\n",
            "synthetic.py",
        )
        == []
    )


@pytest.mark.parametrize("annotation", ["", ": int", ": Final", ": typing.Final"])
def test_public_constants_require_explicit_final_type(annotation: str) -> None:
    namespace = runpy.run_path(str(_PATH))
    findings = namespace["violations"](f"LIMIT{annotation} = 3\n", "source.py")
    assert len(findings) == 1
    assert "Final[T]" in findings[0]


@pytest.mark.parametrize(
    "annotation", ["int", "Final", "Final[int]", "typing.Final", "typing.Final[int]"]
)
def test_private_constants_reject_every_annotation(annotation: str) -> None:
    namespace = runpy.run_path(str(_PATH))
    findings = namespace["violations"](f"_LIMIT: {annotation} = 3\n", "source.py")
    assert len(findings) == 1
    assert "unannotated" in findings[0]


@pytest.mark.parametrize(
    "source",
    [
        "LIMIT: Final[int] = 3\n",
        "LIMIT: typing.Final[int] = 3\n",
        "_LIMIT = 3\n",
        "_LOW = _HIGH = 1\n",
        "_LOW, _HIGH = 0, 1\n",
        "from typing import Final as F\nLIMIT: F[int] = 3\n",
    ],
)
def test_explicit_public_and_unannotated_private_constants_are_valid(
    source: str,
) -> None:
    namespace = runpy.run_path(str(_PATH))
    assert (
        namespace["violations"](
            source,
            "source.py",
            rules=namespace["ALL_RULES"],
        )
        == []
    )


@pytest.mark.parametrize(
    "source",
    [
        "type JSON = dict[str, object]\n",
        "JSON: TypeAlias = dict[str, object]\n",
        "_JSON: typing.TypeAlias = dict[str, object]\n",
        "from typing import TypeAlias as Alias\nJSON: Alias = dict[str, object]\n",
        "from typing import TypeVar\nT = TypeVar('T')\n",
        "import typing as t\nP = t.ParamSpec('P')\n",
        "from typing import TypeVarTuple as TVT\nTS = TVT('TS')\n",
        "from typing import NewType\nID = NewType('ID', int)\n",
        "class Config:\n    LIMIT: int = 3\n",
        "@unique\nclass Status(StrEnum):\n    READY = 'wire-ready-v1'\n",
    ],
)
def test_type_declarations_and_nonmodule_members_are_not_module_constants(
    source: str,
) -> None:
    namespace = runpy.run_path(str(_PATH))
    assert (
        namespace["violations"](source, "source.py", rules=namespace["ALL_RULES"]) == []
    )


@pytest.mark.parametrize(
    "source",
    [
        pytest.param('WIRE_VERSION = "v1"\n', id="string"),
        pytest.param("KINDS = frozenset()\n", id="factory"),
        pytest.param("LOW = HIGH = 1\n", id="chained"),
        pytest.param("LOW, HIGH = 0, 1\n", id="unpacked"),
    ],
)
def test_full_contract_non_numeric_module_constants_also_require_final(
    source: str,
) -> None:
    namespace = runpy.run_path(str(_PATH))
    findings = namespace["violations"](source, "source.py")
    assert findings, "Final is required for constants, not only named magic numbers"
    assert any("Final" in finding for finding in findings)


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("count = 1\n", id="lowercase-unannotated"),
        pytest.param("count: int = 1\n", id="lowercase-annotated"),
        pytest.param("_count: int = 1\n", id="private-lowercase"),
        pytest.param("values = [0, 1, -1]\n", id="numeric-exemptions"),
        pytest.param(
            "from typing import Literal\n"
            'def _mode(value: Literal["r", "w", 2]) -> None:\n    pass\n',
            id="legitimate-literal-annotation",
        ),
        pytest.param(
            "from enum import Flag, IntFlag\n"
            "class Access(Flag):\n    READ = 1\n    WRITE = 2\n"
            "    BOTH = READ | WRITE\n"
            "class Mode(IntFlag):\n    READ = 1\n    ALIAS = 1\n",
            id="flags-are-not-closed-set-enums",
        ),
    ],
)
def test_full_contract_does_not_ban_variables_literals_or_flags(source: str) -> None:
    namespace = runpy.run_path(str(_PATH))
    assert (
        namespace["violations"](source, "source.py", rules=namespace["ALL_RULES"]) == []
    )


@pytest.mark.parametrize(
    "path", ["tests/unit/helper.py", "test_values.py", "values_test.py", "conftest.py"]
)
def test_full_contract_test_numeric_expectations_remain_exempt(path: str) -> None:
    namespace = runpy.run_path(str(_PATH))
    assert (
        namespace["violations"](
            "def check():\n    assert result == 37\n",
            path,
            rules=frozenset({"magic-number"}),
        )
        == []
    ), "Test expectation literals must not be treated as production magic numbers"


@pytest.mark.parametrize("value", ["2", "-2", "1.5"])
def test_full_contract_lowercase_assignment_does_not_hide_magic_numbers(
    value: str,
) -> None:
    namespace = runpy.run_path(str(_PATH))
    findings = namespace["violations"](
        f"count = {value}\n", "source.py", rules=frozenset({"magic-number"})
    )
    assert len(findings) == 1
    assert "magic number" in findings[0]


@pytest.mark.parametrize("base", ["Enum", "StrEnum", "enum.Enum", "enum.StrEnum"])
def test_full_contract_closed_set_enums_require_unique(base: str) -> None:
    namespace = runpy.run_path(str(_PATH))
    source = f'class State({base}):\n    READY = "ready-v1"\n    DONE = "done-v2"\n'
    findings = namespace["violations"](source, "source.py")
    assert findings, f"Closed-set {base} must declare uniqueness"
    assert any("unique" in finding.lower() for finding in findings)


@pytest.mark.parametrize(
    ("imports", "base", "decorator"),
    [
        pytest.param("from enum import Enum, unique", "Enum", "unique", id="enum"),
        pytest.param(
            "from enum import StrEnum, unique", "StrEnum", "unique", id="str-enum"
        ),
        pytest.param("import enum", "enum.StrEnum", "enum.unique", id="qualified"),
        pytest.param(
            "from enum import StrEnum, verify, UNIQUE",
            "StrEnum",
            "verify(UNIQUE)",
            id="verify",
        ),
        pytest.param(
            "import enum",
            "enum.Enum",
            "enum.verify(enum.UNIQUE)",
            id="verify-qualified",
        ),
        pytest.param(
            "from enum import StrEnum as Kind, verify as checked, UNIQUE as distinct",
            "Kind",
            "checked(distinct)",
            id="verify-aliased",
        ),
    ],
)
def test_full_contract_unique_enums_keep_explicit_wire_values(
    tmp_path: Path, imports: str, base: str, decorator: str
) -> None:
    namespace = runpy.run_path(str(_PATH))
    source = dedent(f"""\
        {imports}
        @{decorator}
        class State({base}):
            READY = "wire-ready-v1"
            DONE = "wire-done-v2"
    """)
    target = tmp_path / "source.py"
    target.write_text(source, encoding="utf-8")
    assert namespace["main"]([str(target)]) == 0
    assert target.read_text(encoding="utf-8") == source, (
        "Checking must never rewrite values"
    )


@pytest.mark.parametrize(
    "source",
    [
        (
            "from enum import StrEnum as Kind\n"
            "class State(Kind):\n    READY = 'wire-ready-v1'\n"
        ),
        "import enum as e\nclass State(e.Enum):\n    READY = 1\n",
        (
            "from enum import Enum, verify, CONTINUOUS\n"
            "@verify(CONTINUOUS)\nclass State(Enum):\n    READY = 1\n"
        ),
    ],
)
def test_full_contract_enum_aliases_and_unrelated_verification_do_not_bypass_unique(
    source: str,
) -> None:
    findings = runpy.run_path(str(_PATH))["violations"](source, "source.py")
    assert any("unique" in finding.lower() for finding in findings)


@pytest.mark.parametrize("decorator", ["", "@unique\n        "])
def test_enum_uniqueness_is_checked_in_nested_scopes(decorator: str) -> None:
    source = (
        "def _factory():\n"
        f"    if True:\n        {decorator}class State(StrEnum):\n"
        '            READY = "ready-v1"\n'
    )
    findings = runpy.run_path(str(_PATH))["violations"](source, "source.py")
    assert len(findings) == int(not decorator)
    if findings:
        assert "unique" in findings[0]


@pytest.mark.parametrize(
    ("source", "acronyms"),
    [
        pytest.param("class SmtpFactory: pass\n", "['SMTP']", id="leading"),
        pytest.param("class ApmClient: pass\n", "['APM']", id="toolkit"),
        pytest.param("class LiteLlmAdapter: pass\n", "['LLM']", id="trailing-word"),
        pytest.param("class UrlsConfig: pass\n", "['URL']", id="acronym-plural"),
        pytest.param("class ApisRouter: pass\n", "['API']", id="acronym-plural-api"),
        pytest.param("class SmtpsServer: pass\n", "['SMTPS']", id="secure-smtp"),
        pytest.param(
            "class _DuplicateYamlKeyError(Exception): pass\n", "['YAML']", id="private"
        ),
        pytest.param("class PyJwtVerifier: pass\n", "['JWT']", id="product-prefix"),
        pytest.param(
            "type JsonHttpBody = dict[str, str]\n", "['JSON', 'HTTP']", id="type-alias"
        ),
        pytest.param(
            "from typing import TypeAlias; JsonBody: TypeAlias = dict[str, str]\n",
            "['JSON']",
            id="pep-613-type-alias",
        ),
    ],
)
def test_acronym_case_reports_capitalized_acronyms_by_default(
    source: str, acronyms: str
) -> None:
    findings = runpy.run_path(str(_PATH))["violations"](source, "source.py")

    assert len(findings) == 1, "One finding per misspelled class or type alias name"
    assert findings[0].startswith("source.py:1: "), "Report the declaring line"
    assert acronyms in findings[0], "The finding must name the expected uppercase form"


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("class SMTPFactory: pass\n", id="uppercase"),
        pytest.param("class JSONObject: pass\n", id="acronym-then-word"),
        pytest.param("class LiteLLM: pass\n", id="trailing-acronym"),
        pytest.param("class HttpxTransport: pass\n", id="product-name"),
        pytest.param("class OAuthClient: pass\n", id="oauth-name"),
        pytest.param("class HttpOnlyCookie: pass\n", id="cookie-attribute"),
        pytest.param("class HttpOnlyCookieJar: pass\n", id="cookie-attribute-prefix"),
        pytest.param("class _HttpOnlyCookie: pass\n", id="private-cookie-attribute"),
        pytest.param("class XMLHttpRequest: pass\n", id="standard-name"),
        pytest.param("class XMLHttpRequestShim: pass\n", id="standard-name-prefix"),
        pytest.param("class SMTPSClient: pass\n", id="secure-smtp"),
        pytest.param(
            "class UserId: pass\nclass DbSession: pass\n", id="ambiguous-words"
        ),
        pytest.param(
            "from typing import TypeAlias; JSONBody: TypeAlias = dict[str, str]\n",
            id="pep-613-type-alias",
        ),
        pytest.param("class Rage: pass\nclass Aide: pass\n", id="ordinary-words"),
        pytest.param(
            "def json_loads() -> None: pass\nhttp_client = 1\n", id="non-class"
        ),
    ],
)
def test_acronym_case_accepts_pep8_capwords(source: str) -> None:
    findings = runpy.run_path(str(_PATH))["violations"](
        source, "source.py", rules=frozenset({"acronym-case"})
    )

    assert findings == [], "Uppercase acronyms, product names and words are valid"


@pytest.mark.parametrize(
    ("imports", "base"),
    [
        pytest.param("from enum import StrEnum", "StrEnum", id="imported"),
        pytest.param("import enum", "enum.StrEnum", id="qualified"),
        pytest.param("from enum import StrEnum as Kind", "Kind", id="aliased"),
        pytest.param("import enum as e", "e.StrEnum", id="module-aliased"),
    ],
)
@pytest.mark.parametrize(
    "member",
    [
        pytest.param('READY = "ready"', id="assignment"),
        pytest.param('Ready: str = "ready"', id="annotated-mixed-case"),
    ],
)
def test_enum_auto_reports_matching_strenum_members(
    imports: str, base: str, member: str
) -> None:
    source = f"{imports}\nclass State({base}):\n    {member}\n"
    findings = runpy.run_path(str(_PATH))["violations"](
        source, "source.py", rules=frozenset({"enum-auto"})
    )

    assert len(findings) == 1, "A standard lowercased StrEnum value requires auto()"
    assert findings[0].startswith("source.py:3: "), "Report the member, not the class"
    assert "auto()" in findings[0], "The finding must recommend auto()"


def test_enum_auto_is_enabled_by_default() -> None:
    source = (
        "from enum import StrEnum, unique\n"
        "@unique\n"
        "class State(StrEnum):\n"
        '    READY = "ready"\n'
    )
    findings = runpy.run_path(str(_PATH))["violations"](source, "source.py")

    assert len(findings) == 1, "enum-auto must run without an opt-in rule selection"
    assert findings[0].startswith("source.py:4: ")
    assert "auto()" in findings[0], "Default findings must recommend auto()"


def test_enum_auto_reports_only_matching_members_on_their_own_lines() -> None:
    source = dedent("""\
        from enum import StrEnum, auto
        class State(StrEnum):
            READY = "ready"
            WIRE = "wire-v1"
            GENERATED = auto()
            IN_PROGRESS: str = "in_progress"
        class NotAnEnum:
            READY = "ready"
    """)
    findings = runpy.run_path(str(_PATH))["violations"](
        source, "source.py", rules=frozenset({"enum-auto"})
    )

    assert [finding.split(": ", 1)[0] for finding in findings] == [
        "source.py:3",
        "source.py:6",
    ], "Report every matching enum member, in line order, without unrelated findings"
    assert all("auto()" in finding for finding in findings)


def test_enum_auto_can_be_selected_without_enforcing_unique(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = 'from enum import StrEnum\nclass State(StrEnum):\n    READY = "ready"\n'
    target = tmp_path / "source.py"
    target.write_text(source, encoding="utf-8")

    result = runpy.run_path(str(_PATH))["main"](["--only", "enum-auto", str(target)])

    assert result == 1, "Selecting enum-auto must report a matching explicit value"
    captured = capsys.readouterr()
    assert captured.out == ""
    findings = captured.err.splitlines()
    assert len(findings) == 1, "Selecting enum-auto must not also enforce enum-unique"
    assert findings[0].startswith(f"{target}:3: ")
    assert "auto()" in findings[0]
    assert target.read_text(encoding="utf-8") == source, (
        "Checking must not rewrite values"
    )


@pytest.mark.parametrize("value", ['"wire-ready-v1"', "auto()"])
def test_enum_auto_selected_cli_accepts_safe_values_without_rewriting(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], value: str
) -> None:
    source = (
        f"from enum import StrEnum, auto\nclass State(StrEnum):\n    READY = {value}\n"
    )
    target = tmp_path / "source.py"
    target.write_text(source, encoding="utf-8")

    result = runpy.run_path(str(_PATH))["main"](["--only", "enum-auto", str(target)])

    assert result == 0, "enum-auto must accept auto() and nonmatching wire values"
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert target.read_text(encoding="utf-8") == source, (
        "Checking must not rewrite values"
    )


@pytest.mark.parametrize(
    "member",
    [
        pytest.param("READY = auto()", id="auto"),
        pytest.param("READY: str = auto()", id="annotated-auto"),
        pytest.param('READY = "wire-ready-v1"', id="wire-value"),
        pytest.param('READY = "READY"', id="uppercase-value"),
        pytest.param('READY = "Ready"', id="mixed-case-value"),
        pytest.param('READY = ""', id="empty-value"),
        pytest.param('READY = "ready "', id="trailing-space"),
        pytest.param('IN_PROGRESS = "in-progress"', id="wire-separator"),
        pytest.param('READY = "rea" + "dy"', id="computed-value"),
        pytest.param("READY: str", id="annotation-without-value"),
    ],
)
def test_enum_auto_preserves_values_other_than_exact_matching_literals(
    member: str,
) -> None:
    source = f"from enum import StrEnum, auto\nclass State(StrEnum):\n    {member}\n"
    findings = runpy.run_path(str(_PATH))["violations"](
        source, "source.py", rules=frozenset({"enum-auto"})
    )

    assert findings == [], (
        "Only an exact member-name.lower() string literal is redundant"
    )


@pytest.mark.parametrize(
    ("base", "value"),
    [
        pytest.param("Enum", "1", id="numeric-enum"),
        pytest.param("IntEnum", "1", id="int-enum"),
        pytest.param("Flag", "1", id="flag"),
        pytest.param("IntFlag", "1", id="int-flag"),
        pytest.param("Enum", '"ready"', id="string-valued-enum"),
    ],
)
def test_enum_auto_does_not_change_other_enum_value_conventions(
    base: str, value: str
) -> None:
    source = f"from enum import {base}\nclass State({base}):\n    READY = {value}\n"
    findings = runpy.run_path(str(_PATH))["violations"](
        source, "source.py", rules=frozenset({"enum-auto"})
    )

    assert findings == [], "enum-auto applies only to StrEnum's default generation"


@pytest.mark.parametrize(
    "declaration",
    [
        pytest.param(
            """\
            class State(StrEnum):
                def _generate_next_value_(name, start, count, last_values):
                    return "wire-" + name.lower()
                READY = "ready"
                DONE: str = "done"
            """,
            id="class-defined-generator",
        ),
        pytest.param(
            """\
            from custom_generators import generate
            class State(StrEnum):
                _generate_next_value_ = generate
                READY = "ready"
            """,
            id="assigned-generator",
        ),
        pytest.param(
            """\
            class State(StrEnum):
                _ignore_ = ["READY"]
                READY = "ready"
                DONE = "done"
            """,
            id="ignored-members",
        ),
        pytest.param(
            """\
            class Mixin:
                pass
            class State(Mixin, StrEnum):
                READY = "ready"
            """,
            id="mixed-bases-without-generator",
        ),
        pytest.param(
            """\
            class Mixin:
                def _generate_next_value_(name, start, count, last_values):
                    return "wire-" + name.lower()
            class State(Mixin, StrEnum):
                READY: str = "ready"
            """,
            id="mixed-bases-with-inherited-generator",
        ),
    ],
)
def test_enum_auto_skips_classes_without_known_standard_generation(
    declaration: str,
) -> None:
    source = "from enum import StrEnum\n" + dedent(declaration)
    findings = runpy.run_path(str(_PATH))["violations"](
        source, "source.py", rules=frozenset({"enum-auto"})
    )

    assert findings == [], "Custom generators and mixed bases are unsafe to infer"


def test_conditional_module_constants_keep_visibility_rules() -> None:
    namespace = runpy.run_path(str(_PATH))
    good = "if True:\n    _LIMIT = 3\n    LIMIT: Final[int] = 3\n"
    assert namespace["violations"](good, "source.py") == []
    bad = good.replace("_LIMIT = 3", "_LIMIT: int = 3").replace(
        "LIMIT: Final[int] = 3", "LIMIT: Final = 3"
    )
    findings = namespace["violations"](bad, "source.py")
    assert len(findings) == 2
    assert "unannotated" in findings[0]
    assert "Final[T]" in findings[1]


def test_full_contract_checker_runs_standalone_away_from_checkout(
    tmp_path: Path,
) -> None:
    checker = tmp_path / "check_python.py"
    shutil.copyfile(_PATH, checker)
    target = tmp_path / "source.py"
    target.write_text(
        'LIMIT = 3\n\ndef count() -> int:\n    """Count records.\n\n'
        '    Returns:\n        str: Count of records.\n    """\n    return 1\n',
        encoding="utf-8",
    )
    result = subprocess.run(  # noqa: S603 - fixed checker, synthetic input, no shell
        [sys.executable, "-I", str(checker), "--docstrings", str(target)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert f"{target}:1:" in result.stderr
    assert "Final" in result.stderr
    assert "Returns" in result.stderr


def _one_line(source: str) -> list[str]:
    return runpy.run_path(str(_PATH))["violations"](
        dedent(source), "source.py", rules=frozenset({"docstring-one-line"})
    )


@pytest.mark.parametrize(
    ("source", "sections"),
    [
        pytest.param(
            '''\
            def mapping(value: object) -> dict[str, object]:
                """Parse an object mapping.

                Args:
                    value (object): Untrusted decoded object.

                Returns:
                    dict[str, object]: The string-keyed mapping.

                Raises:
                    ValueError: The data is not a string-keyed object.
                """
                if not isinstance(value, dict):
                    raise ValueError(value)
                return {str(key): item for key, item in value.items()}
            ''',
            "['Args', 'Raises', 'Returns']",
            id="branching-validator",
        ),
        pytest.param(
            '''\
            class Mapper:
                def principal_data(self, principal: Principal) -> dict[str, object]:
                    """Serialize a principal.

                    Args:
                        principal (Principal): Authenticated caller.

                    Returns:
                        dict[str, object]: Wire fields of the principal.
                    """
                    return {"id": principal.id}
            ''',
            "['Args', 'Returns']",
            id="method-receiver-excluded",
        ),
        pytest.param(
            '''\
            def drain(*items: int) -> int:
                """Sum the items.

                Raises:
                    ValueError: No items were supplied.
                """
                if not items:
                    raise ValueError
                return sum(items)
            ''',
            "['Raises']",
            id="variadic-only",
        ),
        pytest.param(
            '''\
            def version() -> str:
                """Read the version.

                Returns:
                    str: Installed version text.
                """
                return load().strip()
            ''',
            "['Returns']",
            id="no-input",
        ),
    ],
)
def test_one_line_rule_flags_sections_on_single_input_callables(
    source: str, sections: str
) -> None:
    findings = _one_line(source)

    assert len(findings) == 1, "Body size no longer exempts a single-input callable"
    assert "takes at most one input" in findings[0]
    assert sections in findings[0], "The finding names the sections to fold"


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            '''\
            def scale(value: float, factor: float) -> float:
                """Convert a measurement.

                Args:
                    value (float): Measurement in source units.
                    factor (float): Target units per source unit.

                Returns:
                    float: Measurement in target units.
                """
                return value * factor
            ''',
            id="two-inputs",
        ),
        pytest.param(
            '''\
            class Store:
                def __init__(self, root: Path) -> None:
                    """Open the store.

                    Args:
                        root (Path): Directory holding the records.
                    """
                    self._root = root
            ''',
            id="initializer",
        ),
        pytest.param(
            '''\
            def mapping(value: object) -> dict[str, object]:
                """Return ``value`` as a string-keyed mapping; raise ``ValueError`` otherwise.

                Nested values are kept as decoded; keys are compared case-sensitively.
                """
                if not isinstance(value, dict):
                    raise ValueError(value)
                return dict(value)
            ''',
            id="prose-only-multi-line",
        ),
        pytest.param(
            '''\
            from typing import overload
            @overload
            def parse(value: str) -> int:
                """Parse text.

                Returns:
                    int: Parsed value.
                """
            ''',
            id="overload-stub",
        ),
    ],
)
def test_one_line_rule_keeps_sections_for_multi_input_and_exempt_callables(
    source: str,
) -> None:
    assert _one_line(source) == []


def test_one_line_property_returns_belong_to_the_property_rule() -> None:
    source = dedent('''\
        class Invoice:
            @property
            def total(self) -> int:
                """Invoice total.

                Returns:
                    int: Net amount plus tax.
                """
                return 1
    ''')
    rules = frozenset({"docstring-one-line", "docstring-property"})
    findings = runpy.run_path(str(_PATH))["violations"](
        source, "source.py", rules=rules
    )

    assert len(findings) == 1, "A property is reported once, by docstring-property"
    assert "property" in findings[0]


def test_one_line_summary_mentioning_raised_error_satisfies_all_docstring_rules() -> (
    None
):
    namespace = runpy.run_path(str(_PATH))
    source = dedent('''\
        def mapping(value: object) -> dict[str, object]:
            """Return ``value`` as a string-keyed mapping; raise ``ValueError`` otherwise."""
            if not isinstance(value, dict):
                raise ValueError(value)
            return dict(value)
    ''')
    rules = frozenset(rule for rule in namespace["ALL_RULES"] if "docstring" in rule)

    assert namespace["violations"](source, "source.py", rules=rules) == []


def _repeated(source: str, path: str = "source.py") -> list[str]:
    return runpy.run_path(str(_PATH))["violations"](
        dedent(source), path, rules=frozenset({"repeated-literal"})
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(
            """\
            def first(kind: str) -> bool:
                return kind == "draft"
            def second(kind: str) -> bool:
                return kind != "draft"
            """,
            ["source.py:4: literal 'draft' is compared 2 times; name it once"],
            id="equality",
        ),
        pytest.param(
            """\
            def check(kind: str, name: str) -> None:
                if kind in ("draft", "final"):
                    pass
                if "draft" not in name:
                    pass
                match kind:
                    case "draft":
                        pass
            """,
            [
                "source.py:4: literal 'draft' is compared 3 times; name it once",
                "source.py:7: literal 'draft' is compared 3 times; name it once",
            ],
            id="membership-and-match-value",
        ),
        pytest.param(
            """\
            def check(code: int, data: bytes) -> None:
                if code == 30 or data == b"ok":
                    pass
                match code, data:
                    case (30, b"ok"):
                        pass
                    case (-2, _) if code != -2:
                        pass
            """,
            [
                "source.py:5: literal 30 is compared 2 times; name it once",
                "source.py:5: literal b'ok' is compared 2 times; name it once",
                "source.py:7: literal -2 is compared 2 times; name it once",
            ],
            id="numbers-bytes-and-negative-patterns",
        ),
        pytest.param(
            """\
            class Reader:
                IS_HIGH = LEVEL == "high"
                def read(self, level: str) -> bool:
                    return level == "high"
            """,
            ["source.py:4: literal 'high' is compared 2 times; name it once"],
            id="class-constants-are-not-module-definitions",
        ),
    ],
)
def test_repeated_literal_reports_each_comparison_after_the_first(
    source: str, expected: list[str]
) -> None:
    assert _repeated(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            """\
            def check(value: object) -> bool:
                return value in (0, 1, -1, "", None, True, False) or (
                    value == 0 or value == 1 or value == -1 or value == ""
                    or value == None or value == True or value == False
                )
            """,
            id="trivial-literals",
        ),
        pytest.param(
            '''\
            """Draft handling."""
            def check(kind: str) -> str:
                """Draft handling."""
                label = f"{kind}draft"
                other = f"draft{kind}"
                return label if kind == "draft" else other
            ''',
            id="docstrings-and-f-string-parts",
        ),
        pytest.param(
            """\
            import os
            _IS_DRAFT = os.environ.get("MODE") == "draft"
            DRAFT_KINDS: Final[frozenset[bool]] = frozenset({"draft" == os.sep})
            def check(kind: str) -> bool:
                return kind == "draft"
            """,
            id="module-constant-definitions",
        ),
        pytest.param(
            """\
            import sys
            if sys.platform == "win32":
                pass
            def native() -> bool:
                return sys.platform != "win32"
            if __name__ == "__main__":
                pass
            if __name__ != "__main__":
                pass
            """,
            id="platform-and-entry-guards",
        ),
        pytest.param(
            """\
            def check(kind: str, limit: int) -> object:
                registry = {"draft": 1}
                emit("draft", "draft")
                return kind < "draft" or limit > 30 or limit >= 30
            """,
            id="non-comparison-and-ordering-uses",
        ),
        pytest.param(
            """\
            def check(first: str, second: str) -> bool:
                return first == "draft" == second
            """,
            id="chained-operand-counts-once",
        ),
    ],
)
def test_repeated_literal_ignores_exempt_and_single_comparisons(source: str) -> None:
    assert _repeated(source) == []


@pytest.mark.parametrize(
    "path", ["tests/unit/helper.py", "test_values.py", "values_test.py", "conftest.py"]
)
def test_repeated_literal_exempts_test_modules(path: str) -> None:
    source = "def check(kind):\n    return kind == 'draft' or kind != 'draft'\n"
    assert _repeated(source, path) == []


def test_repeated_literal_is_opt_in_through_its_cli_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = "def check(kind):\n    return kind == 'draft' or kind != 'draft'\n"
    target = tmp_path / "source.py"
    target.write_text(source, encoding="utf-8")
    main = runpy.run_path(str(_PATH))["main"]

    assert main([str(target)]) == 0, "repeated-literal must stay out of the defaults"
    assert main(["--repeated-literals", str(target)]) == 1
    findings = capsys.readouterr().err.splitlines()
    assert findings == [
        f"{target}:2: literal 'draft' is compared 2 times; name it once"
    ]
