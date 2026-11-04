"""Require useful reasons for comment-based tool suppressions.

This lexical guard checks comments, not native skip/xfail APIs or configuration
values. It does not validate whether a tool accepts a rule or a reason separator.
Tail-consuming directives (cspell, yamllint, hadolint) need a leading reason or
an immediately preceding comment: their tails are never treated as explanations.
Other directives may use the preceding comment across blank lines.
Reasons need at least three words and a non-generic word of at least three
letters; this is a review aid, not proof that an exception is appropriate.

Python uses stdlib tokenization; other supported sources use lexical comment and
quoted-string recognition, not full language parsers (notably JS regex literals
and shell here-documents are not interpreted). Markdown fenced/inline examples are
excluded. Templates use the syntax of their underlying suffix.
"""

import argparse
from collections.abc import Iterator
from dataclasses import dataclass
import io
import os
from pathlib import Path
import re
import sys
import tokenize

_ROOT = Path(__file__).resolve().parents[1]
_SOURCE_ROOTS = {
    "src",
    "scripts",
    "tests",
    "packages",
    ".apm",
    ".agents",
    ".claude",
    ".github",
    ".vscode",
    ".devcontainer",
    "docs",
    "profiles",
    "memories",
}
_EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    ".tox",
    "node_modules",
    "apm_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".ty_cache",
    ".cache",
    "build",
    "dist",
    "htmlcov",
    ".coverage",
}
_GENERATED = {
    ".agents/skills",
    ".claude/skills",
    ".claude/rules",
    ".claude/agents",
    ".github/agents",
    ".github/instructions",
}
_ROOT_DOCS = {
    "AGENTS.md",
    "CHANGELOG.md",
    "CLAUDE.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "GOVERNANCE.md",
    "LICENSE",
    "PROJECT.md",
    "README.md",
    "SECURITY.md",
    "SUPPORT.md",
    "projects.md",
    "llms.txt",
}
_ROOT_CONFIG_SUFFIXES = {".json", ".jsonc", ".yaml", ".yml", ".toml", ".ini", ".cfg"}
_SUFFIXES = {
    ".py",
    ".pyi",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".json",
    ".jsonc",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".md",
    ".mdx",
    ".sh",
    ".bash",
    ".ps1",
    ".tf",
    ".hcl",
    ".dockerfile",
    ".html",
    ".css",
    ".scss",
}
_HASH_SUFFIXES = {
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".sh",
    ".bash",
    ".ps1",
    ".tf",
    ".hcl",
    ".dockerfile",
    "",
}
_SLASH_SUFFIXES = {
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".jsonc",
    ".tf",
    ".hcl",
    ".css",
    ".scss",
}
_QUOTED = r"""'''[\s\S]*?'''|\"\"\"[\s\S]*?\"\"\"|'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*"|`(?:\\.|[^`\\])*`"""
_QUOTES = re.compile(_QUOTED)
_RULES = r"[A-Z]+\d+(?:[ ,]+[A-Z]+\d+)*"
_NAMES = r"[\w@/.-]+(?:\s*,\s*[\w@/.-]+)*"
_DIRECTIVE = re.compile(
    r"(?<![\w-])(?:"
    r"(?P<consuming>cspell\s*:\s*(?:ignore|disable(?:-next-line|-line)?)\b"
    r"|yamllint\s+disable(?:-line|-file)?\b"
    r"|hadolint\s+ignore\s*=\s*(?:DL|SC)\d+(?:,\s*(?:DL|SC)\d+)*)"
    r"|(?:ruff\s*:\s*)?noqa\b(?::\s*" + _RULES + r")?"
    r"|(?:type|ty|pyright)\s*:\s*ignore(?:\[[^\]\n]*\])?"
    r"|pragma\s*:\s*(?:no\s+(?:cover|branch)|allowlist\s+(?:nextline\s+)?secret)\b"
    r"|nosec\b(?:\s+" + _RULES + r")?"
    r"|fmt\s*:\s*(?:off|skip)\b"
    r"|(?:ruff\s*:\s*)?isort\s*:\s*(?:skip_file|skip|off)\b"
    r"|markdownlint-disable(?:-next-line|-line|-file)?\b(?:\s+MD\d+)*"
    r"|zizmor\s*:\s*ignore\[[^\]\n]*\]"
    r"|jscpd\s*:\s*ignore-start\b"
    r"|@ts-(?:expect-error|ignore|nocheck)\b"
    r"|eslint-disable(?:-next-line|-line)?\b(?:\s+" + _NAMES + r")?"
    r"|biome-ignore\s+"
    + _NAMES
    + r"|tflint-ignore\s*:\s*"
    + _NAMES
    + r"|checkov\s*:\s*skip\s*=\s*[\w-]+"
    r"|trivy\s*:\s*ignore\s*:\s*[\w-]+"
    r"|shellcheck\s+disable\s*=\s*SC\d+(?:,\s*SC\d+)*"
    r"|prettier-ignore\b"
    r"|pylint\s*:\s*disable(?:-next)?\s*=\s*" + _NAMES + r"|gitleaks\s*:\s*allow\b"
    r")(?![\w-])",
    re.IGNORECASE,
)
_GENERIC_WORDS = {
    "reviewed",
    "exception",
    "ignore",
    "ignored",
    "okay",
    "allow",
    "allowed",
    "reason",
    "suppression",
    "suppress",
    "justified",
    "needed",
    "necessary",
    "because",
    "this",
    "is",
    "a",
    "an",
    "the",
    "here",
    "has",
    "have",
    "been",
    "was",
    "were",
    "it",
    "we",
    "for",
    "please",
    "lint",
    "linter",
    "rule",
    "rules",
    "disable",
    "disabled",
    "check",
    "checks",
    "skip",
    "skipped",
    "yes",
    "ok",
    "fine",
    "safe",
    "intentional",
    "intentionally",
    "expected",
    "required",
    "requires",
    "need",
    "needs",
    "to",
    "be",
    "not",
    "of",
    "by",
    "on",
    "with",
    "as",
    "at",
    "do",
    "does",
    "can",
    "will",
    "should",
    "must",
    "only",
    "works",
    "work",
}
_MIN_REASON_WORDS = 3
_MIN_WORD_LENGTH = 3
_MESSAGE = "suppression needs a meaningful reason (consuming tails need a leading or immediately preceding comment)"


@dataclass(frozen=True, kw_only=True, slots=True)
class _Comment:
    line: int
    text: str
    standalone: bool


def _python_comments(text: str) -> Iterator[_Comment]:
    lines = text.splitlines()
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type == tokenize.COMMENT:
            line, column = token.start
            yield _Comment(
                line=line,
                text=lines[line - 1][column + 1 :],
                standalone=not lines[line - 1][:column].strip(),
            )


def _comment_pattern(suffix: str) -> re.Pattern[str]:
    parts = []
    if suffix in _HASH_SUFFIXES:
        parts.append(r"\#[^\n]*")
    if suffix in _SLASH_SUFFIXES:
        parts.extend((r"//[^\n]*", r"/\*[\s\S]*?\*/"))
    if suffix in {".md", ".mdx", ".html"}:
        parts.append(r"<!--[\s\S]*?-->")
    comments = "|".join(parts) or r"(?!)"
    # Fenced blocks and code spans in Markdown are examples, not active comments.
    quotes = (
        r"(?P<fence>`{3,}|~{3,})[^\n]*\n[\s\S]*?^[ ]*(?P=fence)[`~]*[ \t]*$|`+[^`]*`+"
        if suffix in {".md", ".mdx"}
        else _QUOTED
    )
    return re.compile(rf"(?:{quotes})|(?P<comment>{comments})", re.MULTILINE)


def _mask_yaml_blocks(text: str) -> str:
    lines = text.splitlines(keepends=True)
    block_indent: int | None = None
    for index, line in enumerate(lines):
        indent = len(line) - len(line.lstrip(" "))
        if block_indent is not None and (not line.strip() or indent > block_indent):
            lines[index] = re.sub(r"[^\n]", " ", line)
            continue
        block_indent = None
        if not line.lstrip().startswith("#") and re.search(
            r"[:-]\s+[|>][1-9+-]*(?:\s*(?:#.*)?)?$", line
        ):
            block_indent = indent
    return "".join(lines)


def _lexical_comments(text: str, *, suffix: str) -> Iterator[_Comment]:
    if suffix in {".yaml", ".yml"}:
        text = _mask_yaml_blocks(text)
    for match in _comment_pattern(suffix).finditer(text):
        comment = match.group("comment")
        if comment is None:
            continue
        prefix = text[text.rfind("\n", 0, match.start()) + 1 : match.start()]
        line = text.count("\n", 0, match.start()) + 1
        content = re.sub(r"^(?:<!--|/\*|//|#)|(?:-->|\*/)$", "", comment)
        for offset, part in enumerate(content.splitlines()):
            yield _Comment(
                line=line + offset,
                text=part.lstrip(" *"),
                standalone=not prefix.strip(),
            )


def _mask_quotes(text: str) -> str:
    return _QUOTES.sub(lambda match: " " * len(match[0]), text)


def _active_directives(text: str) -> list[re.Match[str]]:
    masked = _mask_quotes(text)
    return [
        match
        for match in _DIRECTIVE.finditer(masked)
        if re.search(r"(?:^|[;#]|//)\s*$", masked[: match.start()])
    ]


def _meaningful(text: str) -> bool:
    words = re.findall(r"\b[A-Za-z]+\b", text)
    useful = [
        word
        for word in words
        if len(word) >= _MIN_WORD_LENGTH and word.lower() not in _GENERIC_WORDS
    ]
    return len(words) >= _MIN_REASON_WORDS and bool(useful)


def _reason_parts(text: str) -> tuple[bool, bool, bool]:
    """Return whether a directive exists and its leading/trailing justification."""
    matches = _active_directives(text)
    if not matches:
        return False, _meaningful(text), False
    leading = _meaningful(text[: matches[0].start()])
    # Remove all directives so one suppression cannot justify another.
    tail = text[matches[0].end() :]
    for match in reversed(matches[1:]):
        start = match.start() - matches[0].end()
        end = match.end() - matches[0].end()
        tail = tail[:start] + tail[end:]
    consuming = any(match.group("consuming") is not None for match in matches)
    return True, leading, not consuming and _meaningful(tail)


def _grouped_comments(text: str, *, suffix: str) -> dict[int, _Comment]:
    comments = (
        _python_comments(text)
        if suffix in {".py", ".pyi"}
        else _lexical_comments(text, suffix=suffix)
    )
    grouped: dict[int, _Comment] = {}
    for comment in comments:
        previous = grouped.get(comment.line)
        grouped[comment.line] = _Comment(
            line=comment.line,
            text=f"{previous.text} {comment.text}" if previous else comment.text,
            standalone=previous.standalone if previous else comment.standalone,
        )
    return grouped


def _preceding_reason(
    comment: _Comment, *, lines: list[str], grouped: dict[int, _Comment]
) -> bool:
    previous_line = comment.line - 1
    consuming = any(
        match.group("consuming") is not None
        for match in _active_directives(comment.text)
    )
    while not consuming and previous_line > 0 and not lines[previous_line - 1].strip():
        previous_line -= 1
    previous = grouped.get(previous_line)
    if previous and previous.standalone:
        directive, reason, _ = _reason_parts(previous.text)
        return not directive and reason
    return False


def inspect_text(text: str, *, suffix: str) -> list[tuple[int, str]]:
    """Inspect active comments for unjustified suppressions.

    Args:
        text (str): Source text, including comment delimiters.
        suffix (str): Native file suffix, such as ``.py`` or ``.yaml``.

    Returns:
        One-based line numbers and explanations, at most one per source line.

    Raises:
        tokenize.TokenError: Python tokenization cannot finish.
        IndentationError: Python indentation cannot be tokenized.
    """
    grouped = _grouped_comments(text, suffix=suffix)
    lines = text.splitlines()
    diagnostics = []
    for line, comment in grouped.items():
        active, leading, trailing = _reason_parts(comment.text)
        if not active or leading or trailing:
            continue
        if not _preceding_reason(comment, lines=lines, grouped=grouped):
            diagnostics.append((line, _MESSAGE))
    return diagnostics


def _suffix(path: Path) -> str:
    name = path.name.removesuffix(".template")
    return (
        ".dockerfile"
        if name.lower().startswith("dockerfile")
        else Path(name).suffix.lower()
    )


def _owned_file(path: Path, *, root: Path) -> bool:
    relative = path.relative_to(root)
    if len(relative.parts) == 1:
        return (
            path.name in _ROOT_DOCS
            or path.suffix in _ROOT_CONFIG_SUFFIXES
            or path.name in {".coveragerc", "Dockerfile"}
        )
    return (
        _suffix(path) in _SUFFIXES
        or path.name in _ROOT_DOCS
        or path.name in {".coveragerc", "Dockerfile"}
    )


def _files(root: Path) -> Iterator[Path]:
    def fail(error: OSError) -> None:
        raise error

    for directory, directories, filenames in os.walk(
        root, onerror=fail, followlinks=False
    ):
        parent = Path(directory)
        directories[:] = sorted(
            name
            for name in directories
            if name not in _EXCLUDED_DIRS
            and (parent != root or name in _SOURCE_ROOTS)
            and (parent / name).relative_to(root).as_posix() not in _GENERATED
            and not (parent / name).is_symlink()
        )
        for name in sorted(filenames):
            path = parent / name
            if not path.is_symlink() and _owned_file(path, root=root):
                yield path


def run(root: Path) -> int:
    """Check owned sources, including untracked files, without invoking git.

    Args:
        root (Path): Repository root; only explicit source roots and root
            configuration files and approved documents are included. Dependencies,
            caches, builds, generated native projections and symlinks are excluded.

    Returns:
        Zero on success, one for findings or read, traversal or tokenization errors.
        Errors and findings are written once to stderr as path/line diagnostics.
    """
    if not root.is_dir():
        sys.stderr.write(f"{root}: repository root is not a directory\n")
        return 1
    failed = False
    try:
        for path in _files(root):
            relative = path.relative_to(root).as_posix()
            try:
                diagnostics = inspect_text(
                    path.read_text(encoding="utf-8-sig"), suffix=_suffix(path)
                )
            except (
                OSError,
                UnicodeError,
                tokenize.TokenError,
                IndentationError,
            ) as error:
                sys.stderr.write(f"{relative}: cannot inspect: {error}\n")
                failed = True
                continue
            for line, message in diagnostics:
                sys.stderr.write(f"{relative}:{line}: {message}\n")
                failed = True
    except OSError as error:
        sys.stderr.write(f"{root}: cannot traverse: {error}\n")
        return 1
    return int(failed)


def main(argv: list[str] | None = None) -> int:
    """Return the guard exit code for CLI arguments.

    Args:
        argv (list[str] | None): Arguments, or process arguments when omitted.

    Returns:
        Zero for a clean scan, one for inspection failures or missing reasons.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=_ROOT)
    return run(parser.parse_args(argv).root.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
