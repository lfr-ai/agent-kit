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
_BACKTICK = "`"


def visible_text(value: str) -> bool:
    """Return whether ``value`` is free of hidden control and format characters.

    Tab, newline and carriage return are allowed. ASCII is checked with one
    compiled pattern; only the non-ASCII remainder is classified character by
    character, because format characters (``Cf``) are never ASCII.
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

    Targets come in source order, preserving duplicates and URL escapes but
    removing angle brackets; nothing is yielded without a supported link. This is
    a bounded inline-link scanner, not a complete Markdown parser. It recognizes
    backtick/tilde fences indented by up to three spaces and ignores an unclosed
    fence through the end of the document.
    """
    for match in _MARKDOWN_LINK.finditer("".join(_prose_lines(text))):
        target = match.group("angled") or match.group("bare")
        if target is not None:
            yield target


def _prose_lines(text: str) -> Iterator[str]:
    """Mask fenced code with newlines while preserving unfenced source."""
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
    """Return the opening fence marker; backtick fences reject backtick info."""
    match = _MARKDOWN_FENCE.fullmatch(line.rstrip("\r\n"))
    if match is None:
        return None
    marker = match.group("marker")
    if marker.startswith(_BACKTICK) and _BACKTICK in match.group("info"):
        return None
    return marker


def _closes_fence(line: str, fence: str) -> bool:
    """Report whether a line closes the fence, per CommonMark closing rules."""
    match = _MARKDOWN_FENCE.fullmatch(line.rstrip("\r\n"))
    if match is None:
        return False
    # A closing run uses the opening character and is at least as long.
    closes = match.group("marker").startswith(fence)
    return closes and not match.group("info").strip()
