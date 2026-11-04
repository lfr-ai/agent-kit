from pathlib import Path
import tokenize

import pytest
import scripts.check_suppressions as suppressions
from scripts.check_suppressions import inspect_text

_TRAILING_CASES = (
    "noqa: S603, B010",
    "type: ignore[arg-type]",
    "ty: ignore[invalid-argument-type]",
    "pyright: ignore[reportArgumentType]",
    "pragma: no cover",
    "pragma: no branch",
    "pragma: allowlist secret",
    "pragma: allowlist nextline secret",
    "nosec B603",
    "fmt: off",
    "fmt: skip",
    "isort: skip",
    "isort: off",
    "isort: skip_file",
    "markdownlint-disable MD013",
    "markdownlint-disable-next-line MD013 MD041",
    "zizmor: ignore[template-injection]",
    "jscpd:ignore-start",
    "@ts-expect-error",
    "@ts-ignore",
    "@ts-nocheck",
    "eslint-disable no-console, @typescript-eslint/no-explicit-any",
    "eslint-disable-next-line no-console",
    "biome-ignore lint/suspicious/noExplicitAny",
    "tflint-ignore: terraform_unused_declarations",
    "checkov:skip=CKV_AWS_1",
    "trivy:ignore:AVD-AWS-0001",
    "shellcheck disable=SC1091,SC2086",
    "prettier-ignore",
    "pylint: disable=invalid-name,too-many-arguments",
    "gitleaks:allow",
)
_CONSUMING_CASES = (
    "cspell:ignore word",
    "cspell:disable",
    "cspell:disable-next-line word",
    "yamllint disable rule:line-length",
    "yamllint disable-line rule:line-length",
    "yamllint disable-file",
    "hadolint ignore=DL3052",
)


def _unjustified(lines: list[str], *, suffix: str = ".py") -> list[int]:
    diagnostics = inspect_text("\n".join(lines), suffix=suffix)
    assert all(message.strip() for _, message in diagnostics), (
        "every suppression diagnostic should explain the missing reason"
    )
    return [line for line, _ in diagnostics]


@pytest.mark.parametrize("directive", [*_TRAILING_CASES, *_CONSUMING_CASES])
def test_directives_and_rule_codes_alone_are_unjustified(directive: str) -> None:
    assert _unjustified([f"# {directive}"]) == [1]


@pytest.mark.parametrize("directive", _TRAILING_CASES)
def test_same_line_reason_follows_directive_and_codes(directive: str) -> None:
    assert (
        _unjustified(
            [
                f"value # {directive} -- generated compatibility shim needs this exception"
            ]
        )
        == []
    )


@pytest.mark.parametrize("directive", _TRAILING_CASES)
def test_previous_comment_reason_survives_blank_lines(directive: str) -> None:
    assert (
        _unjustified(
            [
                "  # Generated bindings require this exception for API compatibility.",
                "",
                "  ",
                f"# {directive}",
            ]
        )
        == []
    )


@pytest.mark.parametrize("directive", _CONSUMING_CASES)
def test_consuming_directive_accepts_an_immediately_preceding_reason(
    directive: str,
) -> None:
    assert (
        _unjustified(
            [
                "# Generated bindings require this term for API compatibility.",
                f"# {directive}",
            ]
        )
        == []
    )


@pytest.mark.parametrize("directive", _CONSUMING_CASES)
def test_consuming_directive_does_not_inherit_a_distant_reason(
    directive: str,
) -> None:
    assert _unjustified(
        [
            "# Generated bindings require this term for API compatibility.",
            "",
            f"# {directive}",
        ]
    ) == [3]


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        pytest.param([], [], id="empty-input"),
        pytest.param(["noqa: B010"], [], id="no-comment-marker"),
        pytest.param(["# noqa: B010"], [1], id="ruff-code-is-not-reason"),
        pytest.param(["# type: ignore[arg-type]"], [1], id="type-code-is-not-reason"),
        pytest.param(["# pragma: allowlist secret"], [1], id="secret-is-not-reason"),
        pytest.param(
            ["# Docutils option field; cspell:ignore optionstr"],
            [],
            id="leading-cspell",
        ),
        pytest.param(
            ["# Generated bindings require this exception; noqa: B010"],
            [],
            id="leading-ruff",
        ),
        pytest.param(
            ["# cspell:ignore word -- generated bindings use this project term"],
            [1],
            id="cspell-consumes-tail",
        ),
        pytest.param(
            ["# hadolint ignore=DL3052 -- generated image requires this base"],
            [1],
            id="hadolint-requires-previous",
        ),
        pytest.param(
            ["# yamllint disable -- generated matrix requires long lines"],
            [1],
            id="yamllint-requires-previous",
        ),
        pytest.param(["# okay", "# noqa: B010"], [2], id="generic-previous-word"),
        pytest.param(
            ["# noqa: S603", "# noqa: B010"], [1, 2], id="previous-directive-not-reason"
        ),
        pytest.param(
            ["value # Reviewed exception", "# noqa: B010"],
            [2],
            id="previous-not-comment-only",
        ),
        pytest.param(
            ["# Reviewed exception", "value = 1", "# noqa: B010"],
            [3],
            id="previous-code-breaks-reason",
        ),
        pytest.param(["# noqa: B010 -- ab"], [1], id="two-letter-boundary"),
        pytest.param(
            ["# noqa: B010 -- generated code requires this exception"],
            [],
            id="meaningful-reason",
        ),
        pytest.param(
            ["# noqa: B010 -- reviewed exception"],
            [1],
            id="reviewed-exception-is-not-reason",
        ),
        pytest.param(["# noqa: B010 -- ignore"], [1], id="generic-reason"),
        pytest.param(["# noqa: B010 -- 123 !!!"], [1], id="punctuation-not-reason"),
        pytest.param(
            ["# noqa: B010 # type: ignore[arg-type]"],
            [1],
            id="two-directives-not-reasons",
        ),
        pytest.param(["# Mention `# noqa: B010` in prose."], [], id="backtick-marker"),
        pytest.param(
            ["# Mention `type: ignore[arg-type]` in prose."],
            [],
            id="backtick-directive",
        ),
        pytest.param(['"# example" # noqa: B010'], [1], id="real-marker-after-string"),
        pytest.param(
            ["# noqa: B010 `generated code requires this exception`"],
            [],
            id="quoted-meaningful-reason",
        ),
        pytest.param(
            ["# noqa: B010 `reviewed`"],
            [1],
            id="quoted-generic-reason",
        ),
        pytest.param(["# 'noqa: B010'"], [], id="single-quoted-directive"),
        pytest.param(['# "type: ignore[arg-type]"'], [], id="double-quoted-directive"),
        pytest.param(
            ["\"PGH\", # bans broad suppressions (e.g. '# type: ignore'/'# noqa')"],
            [],
            id="toml-quoted-mentions",
        ),
        pytest.param(["# noqaish: B010"], [], id="word-not-directive"),
        pytest.param(
            ["# noqa: B010", "", "# type: ignore[arg-type]", "# pragma: no cover"],
            [1, 3, 4],
            id="one-based-lines",
        ),
    ],
)
def test_reason_forms_and_prose_boundaries(
    lines: list[str], expected: list[int]
) -> None:
    assert _unjustified(lines) == expected


@pytest.mark.parametrize(
    "directive",
    [
        "markdownlint-enable",
        "markdownlint-restore",
        "yamllint enable",
        "fmt: on",
        "isort: on",
        "cspell:enable",
        "jscpd:ignore-end",
        "eslint-enable",
    ],
)
def test_reenabling_directives_need_no_reason(directive: str) -> None:
    assert _unjustified([f"# {directive}"]) == []


def test_backticks_in_separate_python_comments_cannot_hide_a_directive() -> None:
    assert _unjustified(["# `", "# noqa: F401", "# `"]) == [2]


@pytest.mark.parametrize("separator", [" - ", " -- ", " — ", ": ", " # ", " // "])
def test_reason_separators_are_accepted(separator: str) -> None:
    assert (
        _unjustified(
            [
                f"# noqa: B010{separator}generated compatibility shim needs this exception"
            ]
        )
        == []
    )


@pytest.mark.parametrize(
    ("suffix", "comment"),
    [
        pytest.param(".py", "# noqa: B010", id="python"),
        pytest.param(".ts", "// @ts-ignore", id="typescript"),
        pytest.param(".ts", "/* eslint-disable no-console */", id="typescript-block"),
        pytest.param(".md", "<!-- markdownlint-disable MD013 -->", id="markdown"),
        pytest.param(".yaml", "# yamllint disable rule:line-length", id="yaml"),
        pytest.param(".sh", "# shellcheck disable=SC2086", id="shell"),
        pytest.param(
            ".tf", "# tflint-ignore: terraform_unused_declarations", id="terraform"
        ),
        pytest.param(".dockerfile", "# hadolint ignore=DL3052", id="dockerfile"),
    ],
)
def test_language_specific_comment_syntax_reports_missing_reason(
    suffix: str, comment: str
) -> None:
    assert _unjustified([comment], suffix=suffix) == [1]


@pytest.mark.parametrize(
    ("suffix", "text"),
    [
        pytest.param(
            ".md",
            "Guide text mentions `<!-- markdownlint-disable MD013 -->`.",
            id="markdown-example",
        ),
        pytest.param(".ts", 'const example = "// @ts-ignore";', id="typescript-string"),
        pytest.param(".py", 'example = "# noqa: B010"', id="python-string"),
    ],
)
def test_suppression_examples_in_code_or_docs_are_not_active(
    suffix: str, text: str
) -> None:
    assert inspect_text(text, suffix=suffix) == []


@pytest.mark.parametrize(
    ("suffix", "comment"),
    [
        pytest.param(
            ".ts", "// @ts-ignore -- preserves the generated API", id="typescript"
        ),
        pytest.param(
            ".md",
            "<!-- markdownlint-disable MD013 --> <!-- long generated table -->",
            id="markdown",
        ),
        pytest.param(
            ".yaml",
            "# generated matrix needs long lines; yamllint disable rule:line-length",
            id="yaml-leading-rationale",
        ),
    ],
)
def test_language_specific_reason_forms_are_accepted(suffix: str, comment: str) -> None:
    assert _unjustified([comment], suffix=suffix) == []


@pytest.mark.parametrize(
    ("suffix", "text"),
    [
        (".py", '"""Example:\n# noqa: S603\n"""\nvalue = 1\n'),
        (".py", 'example = """\n# type: ignore[arg-type]\n"""\n'),
        (".toml", 'example = """\n# noqa: S603\n"""\n'),
        (".yaml", "example: |\n  # yamllint disable\nnext: true\n"),
        (".yaml", "example: >-\n  # yamllint disable\nnext: true\n"),
        (".md", "```python\n# noqa: S603\n```\n"),
        (".md", "````md\n```\n<!-- markdownlint-disable MD013 -->\n```\n````\n"),
        (".toml", '"PGH", # blanket noqa and type: ignore comments\n'),
    ],
)
def test_multiline_strings_examples_and_prose_are_not_directives(
    suffix: str, text: str
) -> None:
    assert inspect_text(text, suffix=suffix) == []


@pytest.mark.parametrize(
    ("suffix", "text", "line"),
    [
        (".py", 'example = "# noqa: S603"  # noqa: B010\n', 1),
        (".ts", 'const s = "// @ts-ignore"; // @ts-ignore\n', 1),
        (".yaml", "example: |\n  # yamllint disable\n# yamllint disable\n", 3),
        (".md", "````md\n```\n````\n<!-- markdownlint-disable MD013 -->\n", 4),
        (
            ".py",
            "# generated compatibility needs this exception\n# hadolint ignore=DL3052\n\n# hadolint ignore=DL3052",
            4,
        ),
    ],
)
def test_examples_do_not_hide_following_real_comments(
    suffix: str, text: str, line: int
) -> None:
    assert [number for number, _ in inspect_text(text, suffix=suffix)] == [line]


@pytest.mark.parametrize(
    "relative",
    [
        "src/untracked.py",
        "scripts/untracked.py",
        "tests/untracked.py",
        "packages/example/.apm/skills/example/assets/check.py.template",
        ".apm/skills/example/assets/check.ts.template",
        ".agents/guard/check.py",
        ".github/workflows/check.yml",
        ".claude/settings.yaml",
        "docs/example.md",
        ".pre-commit-config.yaml",
    ],
)
def test_scan_includes_untracked_owned_sources(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], relative: str
) -> None:
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if ".ts" in relative:
        content = "// @ts-ignore\n"
    elif relative.endswith(".md"):
        content = "<!-- markdownlint-disable MD013 -->\n"
    else:
        content = "# noqa: S603\n"
    path.write_text(content, encoding="utf-8")
    assert suppressions.run(tmp_path) == 1
    assert f"{relative}:1:" in capsys.readouterr().err


@pytest.mark.parametrize(
    "relative",
    [
        "node_modules/example/check.py",
        "packages/example/node_modules/check.py",
        "apm_modules/check.py",
        ".venv/check.py",
        ".tox/check.py",
        "build/check.py",
        "dist/check.py",
        "scripts/__pycache__/check.py",
        ".agents/skills/example/check.py",
        ".claude/skills/example/check.py",
        ".claude/rules/example.md",
        ".claude/agents/example.md",
        ".github/agents/example.md",
        ".github/instructions/example.md",
        "research.html",
        "research.html.txt",
        "research.mjs",
    ],
)
def test_scan_excludes_dependencies_generated_outputs_and_research(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], relative: str
) -> None:
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# noqa: S603\n// @ts-ignore\n<!-- markdownlint-disable MD013 -->\n",
        encoding="utf-8",
    )
    assert suppressions.run(tmp_path) == 0
    assert capsys.readouterr().err == ""


def test_scan_reports_bad_encoding_and_keeps_checking(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "a.py").write_bytes(b"\xff")
    (scripts / "b.py").write_text("# noqa: S603\n", encoding="utf-8")
    assert suppressions.run(tmp_path) == 1
    errors = capsys.readouterr().err
    assert "scripts/a.py: cannot inspect:" in errors
    assert "scripts/b.py:1:" in errors


@pytest.mark.parametrize(
    "error", [OSError("read denied"), tokenize.TokenError("unfinished", (1, 0))]
)
def test_scan_reports_read_and_tokenization_failures(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    error: OSError | tokenize.TokenError,
) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/check.py").touch()

    def fail(*args: object, **kwargs: object) -> str:
        raise error

    monkeypatch.setattr(Path, "read_text", fail)
    assert suppressions.run(tmp_path) == 1
    assert "scripts/check.py: cannot inspect:" in capsys.readouterr().err


def test_scan_reports_traversal_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(root: Path) -> list[Path]:
        message = "directory denied"
        raise PermissionError(message)

    monkeypatch.setattr(suppressions, "_files", fail)
    assert suppressions.run(tmp_path) == 1
    assert "cannot traverse: directory denied" in capsys.readouterr().err


def test_cli_checks_explicit_root_and_rejects_missing_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert suppressions.main(["--root", str(tmp_path)]) == 0
    assert suppressions.main(["--root", str(tmp_path / "missing")]) == 1
    assert "not a directory" in capsys.readouterr().err


@pytest.mark.parametrize(
    "reason",
    [
        "this exception has been reviewed",
        "this is intentionally ignored",
        "B010, S603, MD013",
        "123 -- !!!",
    ],
)
def test_generic_text_and_more_codes_are_not_reasons(reason: str) -> None:
    assert _unjustified([f"# noqa: B010 -- {reason}"]) == [1]


def test_native_ruff_file_directive_needs_reason() -> None:
    assert _unjustified(["# ruff: noqa: S603"]) == [1]
    assert (
        _unjustified(
            ["# ruff: noqa: S603 -- generated bindings require this exception"]
        )
        == []
    )


def test_unfinished_python_is_an_explicit_scan_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/check.py").write_text(
        'value = """unfinished\n', encoding="utf-8"
    )
    assert suppressions.run(tmp_path) == 1
    assert "cannot inspect:" in capsys.readouterr().err
