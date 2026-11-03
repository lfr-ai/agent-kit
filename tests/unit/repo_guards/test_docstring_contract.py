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
        "docstring-one-line",
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


def test_rules_are_registered_but_off_by_default() -> None:
    source = dedent('''
        def pair(a: int, b: int) -> int:
            """Add."""
            return a
    ''')
    assert _CHECKER["ALL_RULES"] >= _RULES
    assert _CHECKER["violations"](source, "module.py") == []
    assert _count(source, "docstring-args") == 1


def test_main_enables_docstring_rules_with_flag_and_only(tmp_path: Path) -> None:
    target = tmp_path / "asset.py"
    target.write_text(
        dedent('''
            def pair(a: int, b: int) -> int:
                """Add."""
                return a
        '''),
        encoding="utf-8",
    )
    assert _CHECKER["main"]([str(target)]) == 0
    assert _CHECKER["main"](["--docstrings", str(target)]) == 1
    assert _CHECKER["main"](["--only", "docstring-args", str(target)]) == 1
    assert _CHECKER["main"](["--only", "docstring-one-line", str(target)]) == 0


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
            """Add."""
            return a
        ''',
        """
        def pair(a: int, b: int) -> int:
            return a
        """,
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
            def put(self, a: int, b: int) -> int:
                """Put."""
                return a
        ''',
        '''
        class Box:
            def __init__(self, a: int, b: int) -> None:
                """Create."""
        ''',
        '''
        def f(*args: int, **kwargs: str) -> int:
            """Go."""
            return 1
        ''',
    ],
)
def test_args_section_is_required_and_ordered(source: str) -> None:
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


@pytest.mark.parametrize(
    "source",
    [
        _CONTEXT_EXPANDED,
        '''
        def f(a: int) -> int:
            """Go.

            Args:
                a (int): Value.
            """
            return a
        ''',
        '''
        def f() -> int:
            """Go.

            Returns:
                The count.
            """
            return 1
        ''',
        '''
        def f(a: int) -> None:
            """Go.

            Args:
                a (int): Value.
            """
        ''',
        '''
        class Box:
            def put(self, a: int) -> list[int]:
                """Put.

                Args:
                    a (int): Value.

                Returns:
                    The stored values.
                """
                return [a]
        ''',
        '''
        def f() -> int:
            """Go.

            Args:
                nothing: Nothing.
            """
            return 1
        ''',
    ],
)
def test_obvious_callables_use_a_one_line_docstring(source: str) -> None:
    assert _count(source, "docstring-one-line") == 1


def test_context_example_is_clean_as_one_line() -> None:
    assert _all_clean(_CONTEXT_ONE_LINE)
    assert _count(_CONTEXT_EXPANDED, "docstring-args") == 0


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
def test_one_line_is_not_required_when_the_docstring_adds_detail(
    source: str,
) -> None:
    assert _count(source, "docstring-one-line") == 0
    assert _count(source, "docstring-args") == 0


def test_public_two_parameter_one_liner_needs_args() -> None:
    source = '''
        def pair(a: int, b: int) -> int:
            """Add ``a`` and ``b``."""
            return a
    '''
    assert _count(source, "docstring-args") == 1
    assert _count(source, "docstring-one-line") == 0


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
    bare = f'''
        def f() -> {annotation}:
            """Go."""
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
    assert _count(bare, "docstring-returns") == 1
    assert _count(described, "docstring-returns") == 0


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
            """Go."""
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
        def pair(a: int, b: int) -> int:
            """Add."""
            return a
    '''
    assert _count(source, "docstring-args", path=path) == 0
    assert _count(source, "docstring-args", path="src/thing.py") == 1


def test_checker_asset_satisfies_its_own_docstring_contract() -> None:
    assert _CHECKER["main"](["--docstrings", str(_PATH)]) == 0


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


            def pair(a: int, b: int) -> int:
                """Add."""
                return a
        ''').lstrip(),
        encoding="utf-8",
    )
    assert conventions_module.run(tmp_path) == 1
    assert conventions_module.run(tmp_path, docstrings=True) == 1
    assert conventions_module.run(tmp_path, docstrings=False) == 0
