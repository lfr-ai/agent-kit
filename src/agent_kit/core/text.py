"""Pure text checks and bounded Markdown links for source validation."""

from collections.abc import Iterator
import re
import unicodedata

_ASCII_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ASCII_RUN = re.compile(r"[\x00-\x7f]+")
_HIDDEN_CATEGORIES = frozenset({"Cc", "Cf"})
_MARKDOWN_LINK = re.compile(
    r"!?\[[^\]]*\]\(\s*(?:<(?P<angled>[^>]+)>|(?P<bare>[^\s)]+))"
)
_MARKDOWN_FENCE = re.compile(r" {0,3}(?P<marker>`{3,}|~{3,})(?P<info>.*)")


def visible_text(value: str) -> bool:
    """Reject control and format characters other than tab, newline and return.

    ASCII is checked with one compiled pattern; only the non-ASCII remainder is
    classified character by character, because format characters (``Cf``) are
    never ASCII.

    Args:
        value (str): Decoded text to inspect.

    Returns:
        bool: Whether the text contains no hidden control or format characters.
    """
    if _ASCII_CONTROL.search(value):
        return False
    if value.isascii():
        return True
    return all(
        unicodedata.category(character) not in _HIDDEN_CATEGORIES
        for character in _ASCII_RUN.sub("", value)
    )


def markdown_link_targets(text: str) -> Iterator[str]:
    """Yield inline-style Markdown link/image targets outside fenced code.

    This is a bounded inline-link scanner, not a complete Markdown parser.
    It recognizes backtick/tilde fences indented by up to three spaces and
    ignores an unclosed fence through the end of the document.

    Args:
        text: Markdown source to inspect.

    Yields:
        Targets from the supported inline-link syntax, without angle brackets.
    """
    for match in _MARKDOWN_LINK.finditer("".join(_prose_lines(text))):
        target = match.group("angled") or match.group("bare")
        if target is not None:
            yield target


def _prose_lines(text: str) -> Iterator[str]:
    fence: str | None = None
    for line in text.splitlines(keepends=True):
        if fence is not None:
            if _closes_fence(line, fence):
                fence = None
            yield "\n"
        elif (marker := _opens_fence(line)) is not None:
            fence = marker
            yield "\n"
        else:
            yield line


def _opens_fence(line: str) -> str | None:
    match = _MARKDOWN_FENCE.fullmatch(line.rstrip("\r\n"))
    if match is None:
        return None
    marker = match.group("marker")
    if marker[0] == "`" and "`" in match.group("info"):
        return None
    return marker


def _closes_fence(line: str, fence: str) -> bool:
    match = _MARKDOWN_FENCE.fullmatch(line.rstrip("\r\n"))
    return (
        match is not None
        and match.group("marker")[0] == fence[0]
        and len(match.group("marker")) >= len(fence)
        and not match.group("info").strip()
    )
