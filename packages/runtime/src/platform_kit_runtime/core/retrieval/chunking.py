"""Deterministic markdown-aware chunking with bounded overlap; stdlib only."""

from dataclasses import dataclass, replace
from itertools import pairwise
import re

from platform_kit_runtime.core.retrieval.models import (
    ChunkingConfig,
    RetrievalConfigurationError,
    TextChunk,
)

_MAX_FENCE_INDENT = 3
_HEADING = re.compile(r" {0,3}(?P<marks>#{1,6})(?:[ \t]+(?P<title>.*))?")
_CLOSING_HASHES = re.compile(r"(?:^|[ \t]+)#+$")
_FENCE = re.compile(r" {0,3}(`{3,}|~{3,})")
_COMMENT = re.compile(r"[ \t]*<!--(?:(?!-->).)*-->")
# Split preference: line break, then sentence end, then any whitespace.
_BOUNDARIES = (re.compile(r"\n"), re.compile(r"(?<=[.!?])\s"), re.compile(r"\s"))
_WORD_START = re.compile(r"(?<!\S)\S")
_SECTION_SEPARATOR = " > "
_PARAGRAPH_BREAK = "\n\n"


@dataclass(frozen=True, kw_only=True, slots=True)
class _Piece:
    start: int
    end: int
    level: int = 0
    title: str = ""


def _closes(content: str, fence: str) -> bool:
    stripped = content.strip()
    indent = len(content) - len(content.lstrip(" "))
    return (
        indent <= _MAX_FENCE_INDENT
        and stripped.startswith(fence)
        and set(stripped) == {fence[0]}
    )


class _Blocks:
    """Line scanner grouping text into trimmed heading and content blocks."""

    def __init__(self) -> None:
        """Start without an open block or code fence."""
        self.items: list[_Piece] = []
        self._start = -1
        self._end = -1
        self._fence: str | None = None

    def feed(self, *, line: str, offset: int) -> None:
        """Consume one line, including its terminator, that starts at ``offset``."""
        content = line.rstrip()
        start = offset + len(content) - len(content.lstrip())
        end = offset + len(content)
        fence = self._fence
        if fence is not None:
            # Blank lines stay inside the fence but never end a block.
            if content:
                self._extend(start=start, end=end)
            if _closes(content, fence):
                self._fence = None
                self.flush()
        elif not content or _COMMENT.fullmatch(content):
            self.flush()
        else:
            self._text(content=content, start=start, end=end)

    def flush(self) -> None:
        """Close the open block, if any."""
        if self._start >= 0:
            self.items.append(_Piece(start=self._start, end=self._end))
        self._start = self._end = -1

    def _text(self, *, content: str, start: int, end: int) -> None:
        heading = _HEADING.fullmatch(content)
        if heading:
            self.flush()
            title = _CLOSING_HASHES.sub("", heading["title"] or "").strip()
            level = len(heading["marks"])
            self.items.append(_Piece(start=start, end=end, level=level, title=title))
            return
        fence = _FENCE.match(content)
        if fence:
            self.flush()
            self._fence = fence[1]
        self._extend(start=start, end=end)

    def _extend(self, *, start: int, end: int) -> None:
        if self._start < 0:
            self._start = start
        self._end = max(self._end, end)


def _cut(text: str, *, start: int, stop: int) -> int:
    window = text[start + 1 : stop + 1]
    for boundary in _BOUNDARIES:
        matches = list(boundary.finditer(window))
        if matches:
            return start + 1 + matches[-1].start()
    return stop


def _split(text: str, piece: _Piece, limit: int) -> list[_Piece]:
    pieces: list[_Piece] = []
    start = piece.start
    while piece.end - start > limit:
        cut = _cut(text, start=start, stop=start + limit)
        end = start + len(text[start:cut].rstrip())
        pieces.append(replace(piece, start=start, end=end))
        rest = text[cut : piece.end]
        start = cut + len(rest) - len(rest.lstrip())
    pieces.append(replace(piece, start=start))
    return pieces


def _gap(text: str) -> str:
    # Whitespace stays verbatim; comment-only lines collapse to a paragraph break.
    return text if text.isspace() else _PARAGRAPH_BREAK


class _Packer:
    """Greedy window builder that keeps headings with the content they introduce."""

    def __init__(self, *, text: str, config: ChunkingConfig) -> None:
        """Bind the source text and validated budget.

        Args:
            text (str): Source text that every piece offset refers to.
            config (ChunkingConfig): Window size and overlap budget.
        """
        self._text = text
        self._config = config
        self._window: list[_Piece] = []
        self._start = 0
        self._path: list[_Piece] = []
        self.chunks: list[TextChunk] = []

    def add(self, piece: _Piece) -> None:
        """Append a piece, closing the current window first when required."""
        if self._window and self._breaks_before(piece):
            previous, previous_start = self._window, self._start
            self.close()
            self._start = self._overlap_start(previous, previous_start, piece)
            self._window = [item for item in previous if item.end > self._start]
        if not self._window:
            self._start = piece.start
        self._window.append(piece)
        if piece.level:
            self._path = [
                *(item for item in self._path if item.level < piece.level),
                piece,
            ]

    def close(self) -> None:
        """Emit the current window as a chunk, if it holds any piece."""
        if not self._window:
            return
        parts = [self._text[self._start : self._window[0].end]]
        for before, after in pairwise(self._window):
            parts.extend(
                (
                    _gap(self._text[before.end : after.start]),
                    self._text[after.start : after.end],
                )
            )
        section = _SECTION_SEPARATOR.join(
            item.title for item in self._path if item.title
        )
        self.chunks.append(
            TextChunk(
                text="".join(parts),
                start=self._start,
                end=self._window[-1].end,
                section=section or None,
            )
        )
        self._window = []

    def _breaks_before(self, piece: _Piece) -> bool:
        introduces = piece.level > 0 and any(item.level == 0 for item in self._window)
        oversized = piece.end - self._start > self._config.max_characters
        return introduces or oversized

    def _overlap_start(
        self, previous: list[_Piece], previous_start: int, piece: _Piece
    ) -> int:
        # Context never crosses into a heading; it starts at a word boundary.
        if piece.level:
            return piece.start
        floor = max(
            previous[-1].end - self._config.overlap_characters,
            piece.end - self._config.max_characters,
            previous_start + 1,
        )
        for item in previous:
            # A search range that is empty or before ``floor`` finds no word.
            word = _WORD_START.search(self._text, max(floor, item.start), item.end)
            if word is not None:
                return word.start()
        return piece.start


def chunk_markdown(*, text: str, config: ChunkingConfig) -> tuple[TextChunk, ...]:
    """Split text into ordered chunks along markdown structure.

    Headings start a new chunk and form each chunk's section path; fenced code
    stays together when it fits; oversized blocks split at line, sentence, then
    word boundaries. Overlap repeats at most ``config.overlap_characters`` of
    trailing context after a size split, starting at a word boundary. Comment-only
    lines such as ``<!-- PageBreak -->`` are not chunk content.

    Args:
        text (str): Markdown or plain text, for example OCR layout output.
        config (ChunkingConfig): Character budget and overlap.

    Returns:
        tuple[TextChunk, ...]: Nonblank chunks with strictly increasing offsets;
        empty for blank text.

    Raises:
        RetrievalConfigurationError: ``text`` or ``config`` has the wrong type.
    """
    if not isinstance(text, str) or not isinstance(config, ChunkingConfig):
        raise RetrievalConfigurationError
    blocks = _Blocks()
    offset = 0
    for line in text.splitlines(keepends=True):
        blocks.feed(line=line, offset=offset)
        offset += len(line)
    blocks.flush()
    packer = _Packer(text=text, config=config)
    for block in blocks.items:
        for piece in _split(text, block, config.max_characters):
            packer.add(piece)
    packer.close()
    return tuple(packer.chunks)
