"""Docstring rules are opt-in in the shared checker and default-on in the repo gate."""

from pathlib import Path
import runpy
from textwrap import dedent

import pytest
import scripts.checks.conventions as conventions_module

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
        "docstring-yields",
        "docstring-raises",
        "docstring-raises-extra",
        "docstring-missing",
        "docstring-property",
        "docstring-one-line",
        "docstring-class-sections",
    }
)
_PAIR_ARGS = '''
    def pair(a: int, b: int) -> int:
        """Add.

        Args:
            a (int): First.
            b (int): Second.

        Returns:
            int: Sum of the supplied values.
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
    [("Final", 1), ("Final[int]", 1), ("typing.Final", 1), ("int", 1)],
)
def test_internal_constants_must_be_unannotated(annotation: str, expected: int) -> None:
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
            """Fetch ``key`` through ``client``, forwarding ``refresh`` unchanged."""
            return await client.fetch(key, refresh=refresh)
        ''',
        '''
        def scale(value: float, factor: float) -> float:
            """Multiply ``value`` by a positive unit-conversion ``factor``."""
            return value * factor
        ''',
        '''
        def validate(value: str) -> str:
            """Validate and return the identifier unchanged, without trimming whitespace.

            Require non-empty ASCII text of at most 32 characters.
            """
            return value
        ''',
        '''
        def status() -> int:
            """Report ``0`` on success, ``1`` for invalid input, ``2`` for unavailable storage."""
            return 0
        ''',
    ],
)
def test_summaries_and_prose_describe_contracts_at_any_input_count(source: str) -> None:
    assert _all_clean(source)


@pytest.mark.parametrize("name", ["is_int", "_is_int"])
@pytest.mark.parametrize("result", ["bool", "TypeGuard[int]", "TypeIs[int]"])
def test_concise_predicates_do_not_repeat_signatures(name: str, result: str) -> None:
    source = f'''
        def {name}(value: object) -> {result}:
            """Return whether ``value`` is an integer."""
            return isinstance(value, int)
    '''
    assert _all_clean(source)


@pytest.mark.parametrize(
    "summary",
    [
        "Use ``timeout`` seconds per attempt with at most ``retries`` retries.",
        "Use timeout seconds per attempt with at most retries retries.",
    ],
)
def test_initializer_arguments_can_be_explained_in_one_line(summary: str) -> None:
    source = f'''
        class Client:
            def __init__(self, timeout: float, *, retries: int) -> None:
                """{summary}"""
    '''
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


def test_explanatory_initializer_notes_can_explain_arguments() -> None:
    source = '''
        class Client:
            def __init__(self, timeout: float, *, retries: int) -> None:
                """Create client.

                Notes:
                    Use ``timeout`` seconds per attempt, with at most ``retries`` retries.
                """
    '''
    assert _all_clean(source)


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

            Returns:
                int: The emitted count.
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

                Returns:
                    int: The stored value.
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
            """Wrap the private operation."""
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
    ["a (str): First.", "a (list[int]): First.", "a (int | None): First."],
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


def test_args_may_explain_parameters_without_repeating_their_types() -> None:
    source = '''
        def pair(a: int, b: int) -> int:
            """Add two values.

            Args:
                a: First value.
                b: Second value.
            """
            return a
    '''
    assert _count(source, "docstring-args-type") == 0
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
    def _context(actions: CLIActions) -> int:
        """Emit bounded advisory context; return ``1`` for oversized or unchecked input.

        Use injected ``actions`` to inspect the workspace, never to authorize or
        deny tool calls. Return ``0`` after writing the hook response.
        """
        return 0
'''
_CONTEXT_ONE_LINE = '''
    def _context(actions: CLIActions) -> int:
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
        def f(a: int, b: int) -> int:
            """Go.

            Args:
                a (int): Value.
                b (int): Validation bound.

            Raises:
                ValueError: If bad.

            Returns:
                int: The accepted value, if validation succeeds.
            """
            raise ValueError(a)
        ''',
        '''
        def f(a: int, b: int) -> int:
            """Go.

            Values above the cap are clamped before conversion.

            Args:
                a (int): Value.
                b (int): Upper bound.

            Returns:
                int: The clamped value.
            """
            return a
        ''',
        '''
        def f(a: int, name: str) -> dict[str, int]:
            """Go.

            Args:
                a (int): Value.
                name (str): Result key.

            Returns:
                dict[str, int]: Counts keyed by name.
            """
            return {}
        ''',
        '''
        def f(a: int, b: int) -> Iterator[int]:
            """Go.

            Args:
                a (int): Value to yield.
                b (int): Upper bound.

            Yields:
                int: The supplied value.
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

            Returns:
                int: Sum of the values.
            """
            return a
        ''',
        '''
        def f(a: int, b: int) -> int:
            """Return the supplied value.

            Args:
                a (int): Value to return.
                b (int): Validation bound.

            Returns:
                int: The unchanged value.
            """
            return a
        ''',
    ],
)
def test_contract_details_keep_prose_alongside_optional_sections(
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
def test_structured_returns_may_use_prose_or_typed_sections(
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
                {annotation}: Counts keyed by name.
            """
            return ()
    '''
    assert _count(one_line, "docstring-returns") == 0
    assert _count(bare, "docstring-returns") == 0
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
                """Create a box."""
    '''
    assert _count(source, "docstring-args") == 1
    assert _all_clean(source.replace("Create a box.", "Store the initial value."))


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
def test_plain_returns_accept_concise_or_typed_descriptions(annotation: str) -> None:
    source = f'''
        def f() -> {annotation}:
            """Go."""
            return 1
    '''
    assert _count(source, "docstring-returns") == 0
    described = source.replace(
        '"""Go."""',
        f'"""Go.\n\n            Returns:\n                {annotation}: The result.\n            """',
    )
    assert _count(described, "docstring-returns") == 0


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
                {annotation}: Whether ``value`` has the narrowed shape.
            """
            return True
    '''
    assert _count(bare, "docstring-returns") == 0
    assert _count(described, "docstring-returns") == 0
    assert _count(described, "docstring-returns-none") == 0


def test_generators_document_yields_instead_of_returns() -> None:
    generator = '''
        def f() -> Iterator[tuple[int, int]]:
            """Yield a pair.

            Yields:
                tuple[int, int]: Consecutive values.
            """
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
    assert _count(plain, "docstring-returns") == 0


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
    "decorator", ["property", "cached_property", "functools.cached_property"]
)
def test_property_returns_section_is_rejected(decorator: str) -> None:
    sectioned = f'''
        class Report:
            @{decorator}
            def valid(self) -> bool:
                """Report whether there are no findings.

                Returns:
                    bool: Whether the findings tuple is empty.
                """
                return not self.findings
    '''
    attribute_style = f'''
        class Report:
            @{decorator}
            def valid(self) -> bool:
                """Whether there are no findings."""
                return not self.findings
    '''
    assert _count(sectioned, "docstring-property") == 1
    assert _count(sectioned, "docstring-returns") == 0
    assert _count(attribute_style, "docstring-property") == 0


def test_property_setters_and_methods_keep_their_own_rules() -> None:
    method = '''
        class Report:
            def valid(self) -> bool:
                """Report whether there are no findings.

                Returns:
                    bool: Whether the findings tuple is empty.
                """
                return not self.findings
    '''
    setter = '''
        class Report:
            @valid.setter
            def valid(self, value: bool) -> None:
                """Store the flag.

                Returns:
                    Nothing.
                """
    '''
    assert _count(method, "docstring-property") == 0
    assert _count(setter, "docstring-property") == 0
    assert _count(setter, "docstring-returns-none") == 1


_DIRECT = '''
    def load(path: str, *, strict: bool) -> str:
        """Load a document.

        Raises:
            {documented}: The document is unusable.
        """
        {body}
'''


@pytest.mark.parametrize(
    ("documented", "body"),
    [
        pytest.param("ValueError", "raise ValueError(path)", id="direct"),
        pytest.param(
            "LookupError",
            "try:\n            return read(path)\n"
            "        except KeyError as error:\n"
            "            raise LookupError(path) from error",
            id="translated",
        ),
        pytest.param(
            "OSError",
            "try:\n            return read(path)\n"
            "        except OSError:\n            cleanup()\n            raise",
            id="re-raised",
        ),
        pytest.param("OSError", "raise FileNotFoundError(path)", id="documented-base"),
    ],
)
def test_raises_accepts_direct_translated_and_reraised_errors(
    documented: str, body: str
) -> None:
    source = _DIRECT.format(documented=documented, body=body)
    assert _count(source, "docstring-raises-extra") == 0


@pytest.mark.parametrize(
    ("documented", "body"),
    [
        pytest.param("OSError", "return read(path)", id="callee-failure"),
        pytest.param("SyntaxError", "return ast.unparse(ast.parse(path))", id="stdlib"),
        pytest.param(
            "KeyError",
            "try:\n            return read(path)\n"
            "        except KeyError as error:\n"
            "            raise LookupError(path) from error",
            id="translated-original",
        ),
        pytest.param(
            "ValueError",
            "try:\n            raise ValueError(path)\n"
            "        except ValueError:\n            return ''",
            id="caught-locally",
        ),
        pytest.param(
            "OSError",
            "try:\n            return read(path)\n"
            "        except Exception:\n            cleanup()\n            raise",
            id="callee-failure-through-broad-re-raise",
        ),
    ],
)
def test_raises_rejects_errors_the_body_never_raises(
    documented: str, body: str
) -> None:
    source = _DIRECT.format(documented=documented, body=body)
    assert _count(source, "docstring-raises-extra") == 1


def test_raises_extra_names_imported_exception_classes() -> None:
    source = '''
        from httpx import HTTPError

        def fetch(url: str, *, strict: bool) -> str:
            """Fetch a page.

            Raises:
                {documented}: The upstream request failed.
            """
            raise HTTPError(url)
    '''
    assert _count(source.format(documented="HTTPError"), "docstring-raises-extra") == 0
    assert _count(source.format(documented="OSError"), "docstring-raises-extra") == 1


@pytest.mark.parametrize(
    "body",
    [
        pytest.param("raise _invalid(path)", id="factory"),
        pytest.param("error = build(path)\n        raise error", id="variable"),
        pytest.param(
            "try:\n            return read(path)\n        except:\n            raise",
            id="bare-handler",
        ),
    ],
)
def test_raises_extra_skips_dynamic_exception_types(body: str) -> None:
    source = _DIRECT.format(documented="ValueError", body=body)
    assert _count(source, "docstring-raises-extra") == 0


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            '''
            class Gateway(Protocol):
                def charge(self, amount: int) -> str:
                    """Charge an amount.

                    Raises:
                        PaymentDeclinedError: The provider declined the charge.
                    """
                    ...
            ''',
            id="protocol-stub",
        ),
        pytest.param(
            '''
            class Gateway(Protocol):
                def charge(self, amount: int) -> str:
                    """Charge an amount.

                    Raises:
                        PaymentDeclinedError: The provider declined the charge.
                    """
            ''',
            id="docstring-only",
        ),
        pytest.param(
            '''
            class Gateway(ABC):
                @abc.abstractmethod
                def charge(self, amount: int) -> str:
                    """Charge an amount.

                    Raises:
                        PaymentDeclinedError: The provider declined the charge.
                    """
                    return audit(amount)
            ''',
            id="abstract-method",
        ),
        pytest.param(
            '''
            class Gateway:
                def charge(self, amount: int) -> str:
                    """Charge an amount.

                    Raises:
                        PaymentDeclinedError: The provider declined the charge.
                    """
                    raise NotImplementedError
            ''',
            id="not-implemented",
        ),
    ],
)
def test_raises_on_interface_contracts_is_not_extraneous(source: str) -> None:
    assert _count(source, "docstring-raises-extra") == 0


_DELEGATOR_SECTIONS = '''"""Validate the source tree at ``root``.

        Args:
            root (Path): Source checkout to validate.

        Returns:
            CheckReport: Source findings.
        """'''
_DELEGATOR = """
    {header}
        {doc}
        {body}
"""


@pytest.mark.parametrize(
    ("header", "body"),
    [
        pytest.param(
            "def validate(root: Path) -> CheckReport:",
            "snapshot = Loader().load(root)\n        return Service().validate(snapshot)",
            id="two-statement-function",
        ),
        pytest.param(
            "async def validate(root: Path) -> CheckReport:",
            "return await Service().validate(root)",
            id="awaited",
        ),
        pytest.param(
            "def validate(self, root: Path) -> CheckReport:",
            "return self._service.validate(root)",
            id="method",
        ),
    ],
)
def test_single_input_delegators_use_one_line_docstrings(
    header: str, body: str
) -> None:
    sectioned = _DELEGATOR.format(header=header, doc=_DELEGATOR_SECTIONS, body=body)
    one_line = _DELEGATOR.format(
        header=header, doc='"""Validate the source tree at ``root``."""', body=body
    )
    assert _count(sectioned, "docstring-one-line") == 1
    assert _count(one_line, "docstring-one-line") == 0


@pytest.mark.parametrize(
    ("header", "body", "expected"),
    [
        pytest.param(
            "def validate(root: Path, profile: str) -> CheckReport:",
            "return Service().validate(root, profile)",
            0,
            id="two-inputs",
        ),
        pytest.param(
            "def validate(root: Path) -> CheckReport:",
            "if not root.is_dir():\n            return EMPTY\n"
            "        return Service().validate(root)",
            1,
            id="branching",
        ),
        pytest.param(
            "def validate(root: Path) -> CheckReport:",
            "return root",
            1,
            id="no-forwarded-call",
        ),
        pytest.param(
            "def validate(root: Path) -> CheckReport:",
            "first = Loader().load(root)\n        second = Loader().load(first)\n"
            "        return Service().validate(second)",
            1,
            id="three-statements",
        ),
        pytest.param(
            "def __init__(self, root: Path) -> None:",
            "self._root = Loader().load(root)",
            0,
            id="initializer",
        ),
    ],
)
def test_one_line_rule_follows_input_count_not_body_shape(
    header: str, body: str, expected: int
) -> None:
    source = _DELEGATOR.format(header=header, doc=_DELEGATOR_SECTIONS, body=body)
    assert _count(source, "docstring-one-line") == expected


@pytest.mark.parametrize("section", ["Args", "Raises", "Returns"])
def test_class_docstrings_document_attributes_not_call_sections(section: str) -> None:
    misplaced = f'''
        @dataclass(frozen=True, kw_only=True, slots=True)
        class Usage:
            """Reported token counts.

            {section}:
                total: Sum of prompt and completion counts.
            """

            total: int
    '''
    attributes = misplaced.replace(f"{section}:", "Attributes:")
    assert _count(misplaced, "docstring-class-sections") == 1
    assert _count(attributes, "docstring-class-sections") == 0


def test_validation_failures_are_documented_where_they_are_raised() -> None:
    source = '''
        @dataclass(frozen=True, kw_only=True, slots=True)
        class Message:
            """One text message.

            Attributes:
                content: Text sent to the provider; omitted from repr.
            """

            content: str

            def __post_init__(self) -> None:
                """Validate the message without copying its content.

                Raises:
                    ConfigurationError: The content is not text.
                """
                if not isinstance(self.content, str):
                    raise ConfigurationError
    '''
    assert _all_clean(source)


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
                """Counts keyed by name."""
        ''',
        '''
        class A:
            @override
            def go(self, a: int, b: int) -> dict[str, int]:
                """Go."""
        ''',
        '''
        def outer() -> None:
            """Wrap the private operation."""
            def inner(a: int, b: int) -> dict[str, int]:
                return {}
        ''',
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


def test_conventions_gate_enforces_production_and_portable_docstrings_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _record_checker(monkeypatch)
    assert conventions_module.run(tmp_path) == 0
    assert calls == [
        ("--magic-numbers", "--docstrings"),
        (),
        ("--magic-numbers", "--docstrings"),
        ("--templates", "--magic-numbers", "--docstrings"),
    ]


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


def test_conventions_gate_accepts_concise_public_docs_by_default(
    tmp_path: Path,
) -> None:
    for relative in ("src", "scripts", "tests", ".agents/guard", ".apm", "packages"):
        (tmp_path / relative).mkdir(parents=True)
    (tmp_path / "src/mod.py").write_text(
        dedent('''
            from typing import TypeGuard

            def is_int(value: object) -> TypeGuard[int]:
                """Return whether ``value`` is an integer."""
                return isinstance(value, int)
        '''),
        encoding="utf-8",
    )
    assert conventions_module.run(tmp_path) == 0


# Concise complete prose is valid; typed sections are checked only when supplied.
@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            'def emit(value: int) -> None:\n    """Emit ``value``."""',
            id="function-prose",
        ),
        pytest.param("def emit(value: int) -> None:\n    pass", id="missing-docstring"),
        pytest.param(
            'async def emit(value: int) -> None:\n    """Emit ``value``."""',
            id="async-function",
        ),
        pytest.param(
            "class Client:\n    def emit(self, value: int) -> None:\n"
            '        """Emit ``value``."""',
            id="instance-method",
        ),
        pytest.param(
            "class Client:\n    @classmethod\n"
            '    def emit(cls, value: int) -> None:\n        """Emit ``value``."""',
            id="class-method",
        ),
        pytest.param(
            "class Client:\n    @staticmethod\n"
            '    def emit(value: int) -> None:\n        """Emit ``value``."""',
            id="static-method",
        ),
        pytest.param(
            "class Client:\n    def __init__(self, value: int) -> None:\n"
            '        """Store ``value``."""',
            id="initializer-prose",
        ),
        pytest.param(
            "def emit(value: int, /, *items: str, limit: int = 1, **options: str)"
            ' -> None:\n    """Emit all supplied values."""',
            id="all-parameter-kinds",
        ),
    ],
)
def test_public_parameters_do_not_force_signature_repetition(source: str) -> None:
    assert _count(source, "docstring-args") == 0
    # The existing missing-docstring case must still fail for the right reason.
    assert _count(source, "docstring-missing") == int('"""' not in source)


@pytest.mark.parametrize(
    ("annotation", "body"),
    [
        pytest.param("int", "return 1", id="scalar"),
        pytest.param("str | None", 'return ""', id="optional"),
        pytest.param("list[int]", "return []", id="collection"),
        pytest.param("dict[str, int]", "return {}", id="mapping-one-line"),
        pytest.param("TypeGuard[list[str]]", "return True", id="type-guard"),
        pytest.param("typing.TypeIs[list[str]]", "return True", id="type-is"),
    ],
)
def test_meaningful_returns_may_be_described_by_a_summary(
    annotation: str, body: str
) -> None:
    source = f'''
        def result() -> {annotation}:
            """Report the result."""
            {body}
    '''
    assert _all_clean(source)


@pytest.mark.parametrize(
    "declaration",
    [
        pytest.param("def count(self)", id="instance-method"),
        pytest.param("async def count(self)", id="async-method"),
        pytest.param("@property\n    def count(self)", id="public-property"),
        pytest.param("@classmethod\n    def count(cls)", id="class-method"),
        pytest.param("@staticmethod\n    def count()", id="static-method"),
    ],
)
def test_public_methods_and_properties_may_use_complete_summaries(
    declaration: str,
) -> None:
    source = (
        f"class Client:\n    {declaration} -> int:\n"
        '        """Count available clients."""\n        return 1\n'
    )
    assert _all_clean(source)


@pytest.mark.parametrize(
    "entry",
    [
        pytest.param("str: The resulting count.", id="wrong-type"),
        pytest.param("int:", id="missing-description"),
        pytest.param("", id="empty-section"),
    ],
)
def test_typed_returns_must_match_and_all_returns_need_a_description(
    entry: str,
) -> None:
    source = f'''
        def count() -> int:
            """Count records.

            Returns:
                {entry}
            """
            return 1
    '''
    assert _count(source, "docstring-returns") == 1, (
        "Typed returns must match their annotation and include a meaning"
    )


def test_returns_may_explain_the_value_without_repeating_its_type() -> None:
    source = '''
        def count() -> int:
            """Count records.

            Returns:
                The number of records.
            """
            return 1
    '''
    assert _count(source, "docstring-returns") == 0


def test_yields_may_explain_values_without_repeating_their_type() -> None:
    source = '''
        def values() -> Iterator[int]:
            """Yield each configured value.

            Yields:
                The next configured value.
            """
            yield 1
    '''
    assert _count(source, "docstring-yields") == 0


def test_typed_yields_must_match_the_yielded_type() -> None:
    source = '''
        def values() -> Iterator[int]:
            """Yield each configured value.

            Yields:
                str: The next configured value.
            """
            yield 1
    '''
    assert _count(source, "docstring-yields") == 1


@pytest.mark.parametrize(
    "entry",
    [
        pytest.param("value (int):", id="missing-description"),
        pytest.param("value (int) Count to emit.", id="missing-colon"),
    ],
)
def test_full_contract_args_entries_need_meanings(entry: str) -> None:
    source = f'''
        def emit(value: int) -> None:
            """Emit a count.

            Args:
                {entry}
            """
    '''
    assert _count(source, "docstring-args") == 1, (
        "An Args entry is not complete without a colon and description"
    )


@pytest.mark.parametrize(
    ("prefix", "declaration", "body"),
    [
        pytest.param(
            "",
            "def values(start: int, stop: int) -> Iterator[int]:",
            "yield start",
            id="generator",
        ),
        pytest.param(
            "",
            "def values(start: int, stop: int) -> Iterator[int]:",
            "yield from (start,)",
            id="yield-from",
        ),
        pytest.param(
            "",
            "async def values(start: int, stop: int) -> AsyncIterator[int]:",
            "yield start",
            id="async-generator",
        ),
        pytest.param(
            "@contextmanager\n",
            "def values(start: int, stop: int) -> Iterator[int]:",
            "yield start",
            id="context-manager",
        ),
        pytest.param(
            "@contextlib.asynccontextmanager\n",
            "async def values(start: int, stop: int) -> AsyncIterator[int]:",
            "yield start",
            id="async-context-manager",
        ),
    ],
)
@pytest.mark.parametrize(
    ("section", "expected"),
    [
        pytest.param("", 0, id="missing"),
        pytest.param("\n\n    Yields:\n", 1, id="empty"),
        pytest.param("\n\n    Yields:\n        Values.", 0, id="untyped"),
        pytest.param("\n\n    Yields:\n        str: Values.", 1, id="wrong-type"),
        pytest.param("\n\n    Yields:\n        int:", 1, id="undescribed"),
        pytest.param(
            "\n\n    Returns:\n        Iterator[int]: Values.", 1, id="returns"
        ),
    ],
)
def test_supplied_yields_are_validated_without_requiring_a_section(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    prefix: str,
    declaration: str,
    body: str,
    section: str,
    expected: int,
) -> None:
    target = tmp_path / "source.py"
    target.write_text(
        f'{prefix}{declaration}\n    """Produce values.{section}"""\n    {body}\n',
        encoding="utf-8",
    )
    assert _CHECKER["main"](["--docstrings", str(target)]) == expected
    diagnostic = capsys.readouterr().err
    if expected:
        assert str(target) in diagnostic
        assert ("Returns" if "Returns:" in section else "Yields") in diagnostic
    else:
        assert diagnostic == ""


@pytest.mark.parametrize(
    "section",
    [
        pytest.param("", id="missing"),
        pytest.param("\n\n    Raises:\n", id="empty"),
        pytest.param("\n\n    Raises:\n        ValueError:", id="undescribed"),
    ],
)
def test_explicit_failures_may_use_prose_but_supplied_raises_must_be_described(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], section: str
) -> None:
    target = tmp_path / "source.py"
    target.write_text(
        f'def reject() -> None:\n    """Raise ``ValueError`` for an invalid request.{section}"""\n'
        '    raise ValueError("Invalid request")\n',
        encoding="utf-8",
    )
    assert _CHECKER["main"](["--docstrings", str(target)]) == int(bool(section))
    diagnostic = capsys.readouterr().err
    assert ("Raises" in diagnostic) == bool(section)


@pytest.mark.parametrize(
    "source",
    [
        pytest.param('def flush() -> None:\n    """Flush pending work."""', id="none"),
        pytest.param('def flush():\n    """Flush pending work."""', id="no-return"),
        pytest.param(
            'def flush() -> None:\n    """Flush pending work."""\n    return None',
            id="explicit-none",
        ),
        pytest.param(
            '''
            async def fetch(value: int, /, *items: str, limit: int = 1,
                            **options: str) -> int:
                """Fetch a count.

                Args:
                    value (int): Starting count.
                    *items (str): Items to fetch.
                    limit (int): Maximum count.
                    **options (str): Lookup options.

                Returns:
                    int: The fetched count.

                Raises:
                    LookupError: The requested item is unavailable.
                """
                if not items:
                    raise LookupError(value)
                return await client.fetch(value)
            ''',
            id="typed-async-all-parameter-kinds-direct-error",
        ),
        pytest.param(
            '''
            class Client:
                @classmethod
                def emit(cls, value: int) -> None:
                    """Emit ``value`` counts."""

                def __init__(self, value: int) -> None:
                    """Store a count.

                    Args:
                        value (int): Initial count.
                    """
            ''',
            id="receivers-excluded",
        ),
        pytest.param(
            '''
            @contextmanager
            def values(start: int, stop: int) -> Iterator[int]:
                """Open a value.

                Yields:
                    int: The active value.
                """
                yield 1
            ''',
            id="typed-context-manager",
        ),
        pytest.param(
            '''
            @contextlib.asynccontextmanager
            async def values(start: int, stop: int) -> AsyncIterator[int]:
                """Open a value.

                Yields:
                    int: The active value.
                """
                yield 1
            ''',
            id="typed-async-context-manager",
        ),
        pytest.param(
            '''
            def values(start: int, stop: int) -> Iterator[int]:
                """Return an iterator without yielding.

                Returns:
                    Iterator[int]: The available values.
                """
                def nested() -> Iterator[int]:
                    yield 1
                return nested()
            ''',
            id="nested-yield-is-not-outer-yield",
        ),
        pytest.param(
            '''
            def reject(value: object, reason: str) -> Never:
                """Reject the request.

                Raises:
                    ValueError: The request is invalid.
                """
                raise ValueError("Invalid request")
            ''',
            id="never-returns",
        ),
    ],
)
def test_full_contract_complete_or_trivial_docs_are_accepted(source: str) -> None:
    findings = _CHECKER["violations"](
        dedent(source), "module.py", rules=_CHECKER["ALL_RULES"]
    )
    assert findings == [], f"A complete public contract must stay valid: {findings}"


@pytest.mark.parametrize("section", ["Args", "Returns", "Yields"])
@pytest.mark.parametrize("annotation", [" -> None", ""])
def test_full_contract_no_return_callables_reject_empty_sections(
    section: str, annotation: str
) -> None:
    source = f'''
        def flush(){annotation}:
            """Flush pending work.

            {section}:
            """
    '''
    findings = _CHECKER["violations"](
        dedent(source), "module.py", rules=_CHECKER["ALL_RULES"]
    )
    assert findings, f"Remove the empty {section} section from a trivial callable"
    assert any(section in finding for finding in findings)


@pytest.mark.parametrize("decorator", ["override", "typing.override"])
def test_full_contract_explicit_inherited_documentation_is_exempt(
    decorator: str,
) -> None:
    source = f'''
        class Interface:
            def transform(self, value: int) -> int:
                """Return the transformed ``value`` count."""
                return value

        class Implementation(Interface):
            @{decorator}
            def transform(self, value: int) -> int:
                return value
    '''
    assert (
        _CHECKER["violations"](dedent(source), "module.py", rules=_CHECKER["ALL_RULES"])
        == []
    )


@pytest.mark.parametrize(
    "path", ["tests/unit/helper.py", "test_values.py", "values_test.py", "conftest.py"]
)
def test_full_contract_tests_remain_exempt(path: str) -> None:
    source = "def values(value: int) -> Iterator[int]:\n    yield value\n"
    assert _CHECKER["violations"](source, path, rules=_CHECKER["ALL_RULES"]) == []


@pytest.mark.parametrize("statement", ["raise", "raise error"])
def test_full_contract_reraised_handler_error_is_caller_relevant(
    statement: str,
) -> None:
    source = f'''
        def load() -> None:
            """Load the input.

            Raises:
                ValueError: The input is invalid.
            """
            try:
                read()
            except OSError as error:
                {statement}
    '''
    assert _count(source, "docstring-raises") == 1
    documented = source.replace(
        "ValueError: The input is invalid.",
        "OSError: Reading failed.",
    )
    assert _count(documented, "docstring-raises") == 0


def test_full_contract_caught_and_nested_errors_are_not_public_failures() -> None:
    source = '''
        def load() -> None:
            """Load the input."""
            def nested() -> None:
                raise LookupError()
            try:
                raise ValueError()
            except ValueError:
                pass
    '''
    assert _all_clean(source)


def test_error_caught_inside_a_handler_is_not_an_escaping_failure() -> None:
    source = '''
        def load(source: str, fallback: str) -> None:
            """Load input with local validation recovery.

            Raises:
                OSError: The fallback source cannot be read.
            """
            try:
                read()
            except LookupError:
                try:
                    raise ValueError()
                except ValueError:
                    pass
                raise OSError("fallback unavailable")
    '''
    assert _all_clean(source)


def test_full_contract_raised_error_needs_its_own_description() -> None:
    source = '''
        def load() -> None:
            """Load the input.

            Raises:
                OSError: Reading failed.
            """
            raise ValueError()
    '''
    assert _count(source, "docstring-raises") == 1


@pytest.mark.parametrize("factory", ["_invalid", "MakeError"])
def test_exception_factories_are_not_documented_as_exception_classes(
    factory: str,
) -> None:
    source = f'''
        def {factory}() -> ValueError:
            """Build a safe validation failure."""
            return ValueError()

        def reject(value: object, reason: str) -> None:
            """Reject an invalid value.

            Raises:
                ValueError: The value is invalid.
            """
            raise {factory}()
    '''
    assert _all_clean(source)


def test_failure_prose_can_complement_supplied_raises() -> None:
    source = '''
        def load(source: str, fallback: str) -> None:
            """Load input; raise ``ValueError`` when it is invalid.

            Raises:
                OSError: The source could not be read.
            """
            if invalid():
                raise ValueError()
            raise OSError()
    '''
    assert _all_clean(source)


def test_full_contract_typed_multiline_descriptions_are_valid() -> None:
    source = '''
        def load(value: dict[str, int], defaults: dict[str, int]) -> dict[str, int]:
            """Load the input.

            Args:
                value (dict[str, int]):
                    Input counts.
                defaults (dict[str, int]):
                    Counts for omitted keys.

            Returns:
                dict[str, int]:
                    Counts keyed by name.
            """
            return {**defaults, **value}
    '''
    assert _all_clean(source)


_CAUGHT_SUBCLASS = '''
    def callback() -> None:
        """Consume invalid proof and handle identity failures locally.

        Raises:
            OSError: Reading the input failed.
        """
        try:
            try:
                raise InvalidCallbackError()
            except InvalidCallbackError:
                raise
        except IdentityError:
            pass
'''


def test_full_contract_locally_defined_caught_subclass_does_not_escape() -> None:
    source = (
        "class IdentityError(Exception): pass\n"
        "class InvalidCallbackError(IdentityError): pass\n" + dedent(_CAUGHT_SUBCLASS)
    )
    assert _count(source, "docstring-raises") == 0
    assert (
        _count(
            source.replace("except IdentityError:", "except LookupError:"),
            "docstring-raises",
        )
        == 1
    )


@pytest.mark.parametrize(
    "import_style", ["absolute", "relative", "qualified", "aliased"]
)
def test_full_contract_imported_caught_subclass_does_not_escape(
    tmp_path: Path, import_style: str
) -> None:
    package = tmp_path / "sample"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "errors.py").write_text(
        # The checker must parse definitions, never execute this module.
        'raise RuntimeError("must not import inspected source")\n'
        "class IdentityError(Exception): pass\n"
        "class InvalidCallbackError(IdentityError): pass\n",
        encoding="utf-8",
    )
    imports = {
        "absolute": "from sample.errors import IdentityError, InvalidCallbackError\n",
        "relative": "from .errors import IdentityError, InvalidCallbackError\n",
        "qualified": "import sample.errors as errors\n",
        "aliased": "from sample.errors import IdentityError as Base, InvalidCallbackError as Bad\n",
    }
    body = dedent(_CAUGHT_SUBCLASS)
    if import_style == "qualified":
        body = body.replace(
            "InvalidCallbackError", "errors.InvalidCallbackError"
        ).replace("IdentityError", "errors.IdentityError")
    if import_style == "aliased":
        body = body.replace("InvalidCallbackError", "Bad").replace(
            "IdentityError", "Base"
        )
    target = package / "routes.py"
    source = imports[import_style] + body
    target.write_text(source, encoding="utf-8")
    assert (
        _CHECKER["violations"](
            source, str(target), rules=frozenset({"docstring-raises"})
        )
        == []
    )
    uncaught = (
        source.replace("except IdentityError:", "except LookupError:")
        .replace("except errors.IdentityError:", "except LookupError:")
        .replace("except Base:", "except LookupError:")
    )
    assert (
        len(
            _CHECKER["violations"](
                uncaught, str(target), rules=frozenset({"docstring-raises"})
            )
        )
        == 1
    )


def test_full_contract_owned_templates_and_docstring_examples_are_clean() -> None:
    assets = _PATH.parent
    for path in assets.glob("*.py.template"):
        assert (
            _CHECKER["violations"](
                path.read_text(encoding="utf-8"), str(path), rules=_CHECKER["ALL_RULES"]
            )
            == []
        ), path.name
    examples = (assets.parent / "references/docstrings.md").read_text(encoding="utf-8")
    for block in examples.split("```python\n")[1:]:
        source = block.split("```", 1)[0]
        assert _CHECKER["violations"](source, "example.py", rules=_RULES) == []
