"""Docstring rules are opt-in in the shared checker and default-on in the repo gate."""

from pathlib import Path
import runpy
from textwrap import dedent

import pytest
import scripts.check_conventions as conventions_module

_PATH = (
    Path(__file__).parents[3]
    / "packages/backend/.apm/skills/kit-python-service/assets/check_python.py"
)
_CHECKER = runpy.run_path(str(_PATH))
_RULES = frozenset(
    {
        "docstring-args",
        "docstring-args-type",
        "docstring-returns",
        "docstring-returns-none",
    }
)
_PAIR_ARGS = '''
    def pair(a: int, b: int) -> int:
        """Add.

        Args:
            a (int): First.
            b (int): Second.
        """
        return a
'''


def _count(source: str, rule: str, *, path: str = "module.py") -> int:
    findings = _CHECKER["violations"](dedent(source), path, rules=frozenset({rule}))
    return len(findings)


def _all_clean(source: str) -> bool:
    return _CHECKER["violations"](dedent(source), "module.py", rules=_RULES) == []


@pytest.mark.parametrize(
    ("annotation", "expected"),
    [("Final", 0), ("Final[int]", 0), ("typing.Final", 0), ("int", 1)],
)
def test_internal_constants_allow_only_final_annotations(
    annotation: str, expected: int
) -> None:
    assert _count(f"_LIMIT: {annotation} = 3\n", "private-constant") == expected


@pytest.mark.parametrize(
    "source",
    [
        '''
        def emit(report: CheckReport, stream: TextIO) -> None:
            """Write ``report`` findings to ``stream``, one per line."""
            stream.writelines(report.lines)
        ''',
        '''
        async def fetch(client: Client, key: str, *, refresh: bool = False) -> Item:
            """Delegate lookup to ``client``, forwarding ``refresh`` unchanged."""
            return await client.fetch(key, refresh=refresh)
        ''',
        '''
        def scale(value: float, factor: float) -> float:
            """Multiply ``value`` by a positive unit-conversion ``factor``."""
            return value * factor
        ''',
        '''
        def validate(value: str) -> str:
            """Validate a bounded identifier.

            Args:
                value (str): Non-empty ASCII identifier of at most 32 characters.

            Returns:
                The unchanged identifier; whitespace is not trimmed.
            """
            return value
        ''',
        '''
        def status() -> int:
            """Report the last operation's status.

            Returns:
                ``0`` on success, ``1`` for invalid input, ``2`` for unavailable storage.
            """
            return 0
        ''',
    ],
)
def test_docstring_shape_follows_contract_not_parameter_count(source: str) -> None:
    assert _all_clean(source)


@pytest.mark.parametrize(
    "body",
    [
        "pass",
        '"""Create a bounded client."""',
        '''"""Create a bounded client.

        Args:
        """''',
    ],
)
def test_single_parameter_initializer_requires_documented_argument(body: str) -> None:
    source = f"class Client:\n    def __init__(self, *, timeout: float) -> None:\n        {body}"
    assert _count(source, "docstring-args") == 1


@pytest.mark.parametrize(
    "source",
    [
        '''
        class Failure(ValueError):
            def __init__(self, issue: Issue) -> None:
                """Retain ``issue`` and use its fixed diagnostic as the message."""
                self.issue = issue
                super().__init__(issue.value)
        ''',
        '''
        class Client:
            def __init__(self, timeout: float, *, retries: int) -> None:
                """Use ``timeout`` seconds per attempt, with at most ``retries`` retries."""
                self.timeout = timeout
                self.retries = retries
        ''',
    ],
)
def test_initializer_parameters_may_be_documented_in_concise_prose(source: str) -> None:
    assert _all_clean(source)


@pytest.mark.parametrize(
    "docstring",
    [
        "Create a bounded client.",
        "Use ``timeout_seconds`` seconds per attempt.",
        "Use ``timeout`` seconds per attempt.",
        """Use ``timeout`` seconds with ``retries`` retries.

        Args:
            timeout (float): Timeout in seconds.
        """,
    ],
)
def test_initializer_prose_does_not_hide_undocumented_or_missing_args(
    docstring: str,
) -> None:
    source = f'''
        class Client:
            def __init__(self, timeout: float, *, retries: int) -> None:
                """{docstring}"""
    '''
    assert _count(source, "docstring-args") == 1


@pytest.mark.parametrize("section", ["See Also", "References", "Example", "Examples"])
@pytest.mark.parametrize(
    ("prose", "mentions"),
    [
        ("Create client.", "``timeout`` and ``retries``"),
        ("Use ``timeout`` seconds per attempt.", "``retries``"),
    ],
)
def test_reference_and_example_mentions_do_not_document_initializer_parameters(
    section: str, prose: str, mentions: str
) -> None:
    source = f'''
        class Client:
            def __init__(self, timeout: float, *, retries: int) -> None:
                """{prose}

                {section}:
                    Look up {mentions} in the client guide.
                """
    '''
    assert _count(source, "docstring-args") == 1


@pytest.mark.parametrize("indent", ["    ", "\t"])
@pytest.mark.parametrize("annotation", ["int", "str"])
@pytest.mark.parametrize("section", ["", "Notes:\n        No conversion is performed."])
def test_malformed_supplied_args_header_is_not_ignored(
    indent: str, annotation: str, section: str
) -> None:
    source = f'''
def add(a: int, b: int) -> int:
    """Add two values.

    Both values are added without conversion.

    {section}

    {indent}Args:
    {indent}    a ({annotation}): First value.
    {indent}    b ({annotation}): Second value.
    """
    return a + b
'''
    assert _count(source, "docstring-args") == 1


def test_explanatory_initializer_prose_may_precede_references() -> None:
    assert _all_clean('''
        class Client:
            def __init__(self, timeout: float, *, retries: int) -> None:
                """Use ``timeout`` seconds per attempt, with at most ``retries`` retries.

                See Also:
                    The client guide describes deployment defaults.
                """
    ''')


def test_explanatory_initializer_notes_may_document_parameters() -> None:
    assert _all_clean('''
        class Client:
            def __init__(self, timeout: float, *, retries: int) -> None:
                """Create client.

                Notes:
                    Use ``timeout`` seconds per attempt, with at most ``retries`` retries.
                """
    ''')


def test_args_header_inside_an_example_is_not_a_supplied_section() -> None:
    assert _all_clean('''
        def add(a: int, b: int) -> int:
            """Add ``a`` and ``b``.

            Examples:
                A different callable might document strings:

                    Args:
                        a (str): First value.
                        b (str): Second value.
            """
            return a + b
    ''')


def test_rules_are_registered_but_off_by_default() -> None:
    source = dedent('''
        class Client:
            def __init__(self, *, timeout: float) -> None:
                """Create a bounded client."""
    ''')
    assert _CHECKER["ALL_RULES"] >= _RULES
    assert _CHECKER["violations"](source, "module.py") == []
    assert _count(source, "docstring-args") == 1


def test_main_enables_docstring_rules_with_flag_and_only(tmp_path: Path) -> None:
    target = tmp_path / "asset.py"
    target.write_text(
        dedent('''
            class Client:
                def __init__(self, *, timeout: float) -> None:
                    """Create a bounded client."""
        '''),
        encoding="utf-8",
    )
    assert _CHECKER["main"]([str(target)]) == 0
    assert _CHECKER["main"](["--docstrings", str(target)]) == 1
    assert _CHECKER["main"](["--only", "docstring-args", str(target)]) == 1
    assert _CHECKER["main"](["--only", "docstring-returns", str(target)]) == 0


def test_compliant_documents_are_clean() -> None:
    assert _all_clean(_PAIR_ARGS)
    assert _all_clean('''
        def f(*args: int, **kwargs: str) -> int:
            """Go.

            Args:
                *args (int): Values.
                **kwargs (str): Options.
            """
            return 1
    ''')
    assert _all_clean('''
        class Box:
            def put(self, a: int, b: int) -> int:
                """Put.

                Args:
                    a (int): First.
                    b (int): Second.
                """
                return a
    ''')


@pytest.mark.parametrize(
    "source",
    [
        '''
        def pair(a: int, b: int) -> int:
            """Add.

            Args:
                b (int): Second.
                a (int): First.
            """
            return a
        ''',
        '''
        def pair(a: int, b: int) -> int:
            """Add.

            Args:
                a (int): First.
            """
            return a
        ''',
        '''
        def _pair(a: int, b: int) -> int:
            """Add.

            Args:
                a (int): First.
            """
            return a
        ''',
        '''
        def outer() -> None:
            def inner(a: int, b: int) -> int:
                """Add.

                Args:
                    b (int): Second.
                """
                return a
        ''',
        '''
        class Box:
            def __init__(self, a: int, b: int) -> None:
                """Create."""
        ''',
        '''
        def f(*args: int, **kwargs: str) -> int:
            """Go.

            Args:
                args (int): Values.
                kwargs (str): Options.
            """
            return 1
        ''',
        '''
        def f(value: int) -> int:
            """Go.

            Args:
                value (int): Value.
                extra (int): Not a parameter.
            """
            return value
        ''',
        '''
        def f(value: int) -> int:
            """Go.

            Args:
                value (int): Value.
                value (int): Repeated.
            """
            return value
        ''',
        '''
        def f(value: int) -> int:
            """Go.

            Args:
            """
            return value
        ''',
    ],
)
def test_supplied_args_are_complete_and_ordered(source: str) -> None:
    assert _count(source, "docstring-args") == 1


@pytest.mark.parametrize(
    "source",
    [
        '''
        def _pair(a: int, b: int) -> int:
            """Add ``a`` and ``b``."""
            return a
        ''',
        '''
        class _Box:
            def put(self, a: int, b: int) -> int:
                """Put ``a`` beside ``b``."""
                return a
        ''',
        '''
        def outer() -> None:
            """Wrap."""

            def inner(a: int, b: int) -> int:
                """Add ``a`` and ``b``."""
                return a
        ''',
    ],
)
def test_private_and_nested_callables_may_use_one_line(source: str) -> None:
    assert _all_clean(source)


@pytest.mark.parametrize(
    "entry",
    ["a: First.", "a (str): First.", "a (list[int]): First.", "a (int | None): First."],
)
def test_args_type_must_equal_the_annotation(entry: str) -> None:
    source = f'''
        def pair(a: int, b: int) -> int:
            """Add.

            Args:
                {entry}
                b (int): Second.
            """
            return a
    '''
    assert _count(source, "docstring-args-type") == 1
    assert _count(source, "docstring-args") == 0


def test_args_type_message_names_the_expected_entry() -> None:
    source = dedent('''
        def pair(a: int, b: dict[str,int] | None) -> int:
            """Add.

            Args:
                a (str): First.
                b (dict[str, int] | None): Second.
            """
            return a
    ''')
    findings = _CHECKER["violations"](
        source, "m.py", rules=frozenset({"docstring-args-type"})
    )
    assert len(findings) == 1
    assert "a (int)" in findings[0]


def test_args_type_ignores_whitespace_and_quotes() -> None:
    source = '''
        def pair(a: dict[str,int], b: "int") -> int:
            """Add.

            Args:
                a (dict[str,   int]): First.
                b ('int'): Second.
            """
            return 1
    '''
    assert _count(source, "docstring-args-type") == 0
    assert _count(source, "docstring-args") == 0


_CONTEXT_EXPANDED = '''
    def _context(actions: CliActions) -> int:
        """Emit bounded advisory context without authorizing or denying tool calls.

        Args:
            actions (CliActions): Injected operations; ``context`` inspects the workspace.

        Returns:
            int: ``0`` after writing the hook response, ``1`` when input is too large or
            cannot be checked.
        """
        return 0
'''
_CONTEXT_ONE_LINE = '''
    def _context(actions: CliActions) -> int:
        """Write SessionStart context; return ``1`` if stdin is oversized or invalid."""
        return 0
'''


@pytest.mark.parametrize("source", [_CONTEXT_ONE_LINE, _CONTEXT_EXPANDED])
def test_context_may_be_concise_without_forbidding_failure_details(source: str) -> None:
    assert _all_clean(source)


@pytest.mark.parametrize(
    "source",
    [
        '''
        def f(a: int) -> int:
            """Go.

            Args:
                a (int): Value.

            Raises:
                ValueError: If bad.
            """
            raise ValueError(a)
        ''',
        '''
        def f(a: int) -> int:
            """Go.

            Values above the cap are clamped before conversion.

            Args:
                a (int): Value.
            """
            return a
        ''',
        '''
        def f(a: int) -> dict[str, int]:
            """Go.

            Args:
                a (int): Value.

            Returns:
                Counts keyed by name.
            """
            return {}
        ''',
        '''
        def f(a: int) -> Iterator[int]:
            """Go.

            Yields:
                Values.
            """
            yield a
        ''',
        '''
        class Box:
            def __init__(self, a: int) -> None:
                """Create.

                Args:
                    a (int): Value.
                """
        ''',
        '''
        def pair(a: int, b: int) -> int:
            """Add.

            Args:
                a (int): First.
                b (int): Second.
            """
            return a
        ''',
        '''
        def f(a: int) -> int:
            """Go."""
            return a
        ''',
    ],
)
def test_contract_details_may_use_prose_or_sections(
    source: str,
) -> None:
    assert _all_clean(source)


@pytest.mark.parametrize(
    "annotation",
    [
        "tuple[int, str]",
        "dict[str, int]",
        "Mapping[str, int]",
        "list[list[int]]",
        "Callable[[int], str]",
        "int | str",
        "dict[str, int] | None",
        "Optional[tuple[int, int]]",
        "Union[int, str]",
    ],
)
def test_structured_returns_require_a_described_returns_section(
    annotation: str,
) -> None:
    one_line = f'''
        def f() -> {annotation}:
            """Return counts keyed by name."""
            return ()
    '''
    bare = f'''
        def f() -> {annotation}:
            """Go.

            Counting skips empty names.
            """
            return ()
    '''
    described = f'''
        def f() -> {annotation}:
            """Go.

            Returns:
                Counts keyed by name.
            """
            return ()
    '''
    assert _count(one_line, "docstring-returns") == 0
    assert _count(bare, "docstring-returns") == 1
    assert _count(described, "docstring-returns") == 0


@pytest.mark.parametrize("body", ["", "    ", "\n"])
def test_empty_returns_section_does_not_describe_a_structured_result(body: str) -> None:
    source = f'''
        def counts() -> dict[str, int]:
            """Count entries.

            Returns:
                {body}
            """
            return {{}}
    '''
    assert _count(source, "docstring-returns") == 1


@pytest.mark.parametrize("name", ["Box", "_Box"])
def test_initializer_contract_is_independent_of_class_visibility(name: str) -> None:
    source = f'''
        class {name}:
            def __init__(self, value: str = "") -> None:
                """Store the initial value."""
    '''
    assert _count(source, "docstring-args") == 1


def test_parameterless_initializer_needs_no_args_section() -> None:
    assert _all_clean('''
        class Box:
            def __init__(self) -> None:
                """Create an empty box."""
    ''')


@pytest.mark.parametrize(
    "annotation",
    ["int", "str | None", "list[int]", "tuple[int, ...]", "Path", "Literal['a', 'b']"],
)
def test_plain_returns_need_no_returns_section(annotation: str) -> None:
    source = f'''
        def f() -> {annotation}:
            """Go."""
            return 1
    '''
    assert _count(source, "docstring-returns") == 0


@pytest.mark.parametrize(
    "annotation",
    [
        "TypeGuard[list[str]]",
        "TypeIs[dict[str, int]]",
        "typing.TypeGuard[list[str]]",
        "typing.TypeIs[tuple[int, str]]",
    ],
)
def test_type_predicates_are_bool_like_and_may_keep_returns(annotation: str) -> None:
    bare = f'''
        def f(value: object) -> {annotation}:
            """Check ``value``."""
            return True
    '''
    described = f'''
        def f(value: object) -> {annotation}:
            """Check ``value``.

            Returns:
                Whether ``value`` has the narrowed shape.
            """
            return True
    '''
    assert _count(bare, "docstring-returns") == 0
    assert _count(described, "docstring-returns") == 0
    assert _count(described, "docstring-returns-none") == 0


def test_generators_document_yields_instead_of_returns() -> None:
    generator = '''
        def f() -> Iterator[tuple[int, int]]:
            """Go."""
            yield 1, 2
    '''
    plain = '''
        def f() -> Iterator[tuple[int, int]]:
            """Go.

            The iterator is empty.
            """
            return iter(())
    '''
    assert _count(generator, "docstring-returns") == 0
    assert _count(plain, "docstring-returns") == 1


def test_returns_is_rejected_on_none() -> None:
    bad = '''
        def f() -> None:
            """Go.

            Returns:
                Nothing.
            """
    '''
    good = '''
        def f() -> None:
            """Go."""
    '''
    assert _count(bad, "docstring-returns-none") == 1
    assert _count(good, "docstring-returns-none") == 0


@pytest.mark.parametrize(
    "source",
    [
        '''
        class A:
            def __eq__(self, a: int, b: int) -> dict[str, int]:
                """Compare."""
        ''',
        """
        @overload
        def f(a: int, b: int) -> dict[str, int]: ...
        """,
        '''
        class A:
            @property
            def v(self) -> dict[str, int]:
                """Value."""
        ''',
        '''
        class A:
            @override
            def go(self, a: int, b: int) -> dict[str, int]:
                """Go."""
        ''',
        """
        def outer() -> None:
            def inner(a: int, b: int) -> dict[str, int]:
                return {}
        """,
        """
        def _helper(a: int, b: int) -> int:
            return a
        """,
    ],
)
def test_exempt_callables_are_not_flagged(source: str) -> None:
    assert _all_clean(source)


@pytest.mark.parametrize(
    "path", ["tests/unit/helper.py", "test_thing.py", "thing_test.py", "conftest.py"]
)
def test_test_modules_are_exempt(path: str) -> None:
    source = '''
        class Client:
            def __init__(self, *, timeout: float) -> None:
                """Create a bounded client."""
    '''
    assert _count(source, "docstring-args", path=path) == 0
    assert _count(source, "docstring-args", path="src/thing.py") == 1


def test_checker_asset_satisfies_its_own_docstring_contract() -> None:
    assert _CHECKER["main"](["--docstrings", str(_PATH)]) == 0


def test_documentation_example_satisfies_the_shared_docstring_contract() -> None:
    path = (
        Path(__file__).parents[3]
        / "packages/shared/.apm/skills/kit-documentation/assets/docstrings.py.template"
    )
    assert _CHECKER["main"](["--templates", "--docstrings", str(path)]) == 0


def _record_checker(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[str, ...]]:
    calls: list[tuple[str, ...]] = []

    def run_checker(paths: tuple[Path, ...], *, options: tuple[str, ...] = ()) -> int:
        calls.append(options)
        return 0

    monkeypatch.setattr(conventions_module, "_run_checker", run_checker)
    return calls


def _docstring_scopes(calls: list[tuple[str, ...]]) -> list[bool]:
    return ["--docstrings" in options for options in calls]


def test_conventions_gate_enforces_production_and_portable_docstrings_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _record_checker(monkeypatch)
    assert conventions_module._DOCSTRINGS_ENABLED is True
    assert conventions_module.run(tmp_path) == 0
    assert calls == [
        ("--magic-numbers", "--docstrings"),
        (),
        ("--magic-numbers", "--docstrings"),
        ("--templates", "--magic-numbers", "--docstrings"),
    ]


def test_conventions_gate_enables_docstrings_by_constant_or_argument(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _record_checker(monkeypatch)
    enforced = [True, False, True, True]
    conventions_module.run(tmp_path, docstrings=True)
    assert _docstring_scopes(calls) == enforced
    calls.clear()
    conventions_module.run(tmp_path, docstrings=False)
    assert not any(_docstring_scopes(calls))
    calls.clear()
    monkeypatch.setattr(conventions_module, "_DOCSTRINGS_ENABLED", False)
    conventions_module.run(tmp_path)
    assert not any(_docstring_scopes(calls))
    calls.clear()
    conventions_module.run(tmp_path, docstrings=True)
    assert _docstring_scopes(calls) == enforced


def test_conventions_gate_rejects_missing_args_by_default(
    tmp_path: Path,
) -> None:
    for relative in ("src", "scripts", "tests", ".agents/guard", ".apm", "packages"):
        (tmp_path / relative).mkdir(parents=True)
    (tmp_path / "src/mod.py").write_text(
        dedent('''
            """Module."""


            class Client:
                def __init__(self, *, timeout: float) -> None:
                    """Create a bounded client."""
        ''').lstrip(),
        encoding="utf-8",
    )
    assert conventions_module.run(tmp_path) == 1
    assert conventions_module.run(tmp_path, docstrings=True) == 1
    assert conventions_module.run(tmp_path, docstrings=False) == 0
