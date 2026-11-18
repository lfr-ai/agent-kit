from collections.abc import Callable
from itertools import pairwise
from typing import Final

from hypothesis import assume, given
from hypothesis import strategies as st
import pytest

from platform_kit_runtime.retrieval import (
    ChunkingConfig,
    RetrievalConfigurationError,
    TextChunk,
    chunk_markdown,
)

pytestmark = pytest.mark.unit

LINES: Final[st.SearchStrategy[str]] = st.one_of(
    st.text(alphabet="ab .!?\t", max_size=40),
    st.sampled_from(
        ["# Title", "## Sub ##", "###", "```", "~~~~", "    ```", "", "  ", "- item"]
    ),
)
MARKDOWN: Final[st.SearchStrategy[str]] = st.lists(LINES, max_size=40).map("\n".join)
CONFIGS: Final[st.SearchStrategy[ChunkingConfig]] = st.integers(
    min_value=1, max_value=120
).flatmap(
    lambda size: st.builds(
        ChunkingConfig,
        max_characters=st.just(size),
        overlap_characters=st.integers(min_value=0, max_value=size - 1),
    )
)


def spans(chunks: tuple[TextChunk, ...]) -> list[tuple[str, int, int, str | None]]:
    return [(chunk.text, chunk.start, chunk.end, chunk.section) for chunk in chunks]


def assert_invariants(text: str, config: ChunkingConfig) -> tuple[TextChunk, ...]:
    chunks = chunk_markdown(text=text, config=config)
    assert chunks == chunk_markdown(text=text, config=config)
    for chunk in chunks:
        assert chunk.text == text[chunk.start : chunk.end]
        assert 0 < len(chunk.text) <= config.max_characters
        assert chunk.text == chunk.text.strip()
    for before, after in pairwise(chunks):
        assert before.start < after.start
        assert before.end < after.end
        assert before.end - after.start <= config.overlap_characters
    covered = {index for chunk in chunks for index in range(chunk.start, chunk.end)}
    assert all(
        index in covered
        for index, character in enumerate(text)
        if not character.isspace()
    )
    return chunks


@pytest.mark.property
@given(text=MARKDOWN, config=CONFIGS)
def test_markdown_chunks_are_bounded_ordered_and_complete(
    text: str, config: ChunkingConfig
) -> None:
    assert_invariants(text, config)


@pytest.mark.property
@given(text=st.text(max_size=300), config=CONFIGS)
def test_arbitrary_unicode_chunks_keep_invariants(
    text: str, config: ChunkingConfig
) -> None:
    assume("<!--" not in text)
    assert_invariants(text, config)


def test_headings_start_chunks_and_form_section_paths() -> None:
    text = "# Guide\n\nIntro text.\n\n## Setup ##\n\nInstall it.\n\n# Other\n\nMore."
    chunks = chunk_markdown(text=text, config=ChunkingConfig())
    assert spans(chunks) == [
        ("# Guide\n\nIntro text.", 0, 20, "Guide"),
        ("## Setup ##\n\nInstall it.", 22, 46, "Guide > Setup"),
        ("# Other\n\nMore.", 48, 62, "Other"),
    ]


def test_consecutive_headings_stay_with_their_content() -> None:
    chunks = chunk_markdown(text="# A\n## B\nbody\n#\nend", config=ChunkingConfig())
    assert spans(chunks) == [
        ("# A\n## B\nbody", 0, 13, "A > B"),
        ("#\nend", 14, 19, None),
    ]


def test_fenced_code_is_not_parsed_as_headings() -> None:
    text = "```python\n# not a heading\n```\nafter"
    chunks = chunk_markdown(text=text, config=ChunkingConfig())
    assert spans(chunks) == [(text, 0, len(text), None)]


def test_unclosed_fence_ignores_trailing_blank_lines() -> None:
    text = "```\ncode\n\n  \n"
    chunks = chunk_markdown(text=text, config=ChunkingConfig())
    assert spans(chunks) == [("```\ncode", 0, 8, None)]


def test_only_the_opening_fence_marker_closes_and_resumes_headings() -> None:
    text = "~~~\n```\n# still code\n~~~\n# After\nbody"
    chunks = chunk_markdown(text=text, config=ChunkingConfig())
    assert spans(chunks) == [
        ("~~~\n```\n# still code\n~~~", 0, 24, None),
        ("# After\nbody", 25, 37, "After"),
    ]


def test_comment_lines_are_separators_not_content() -> None:
    text = "Page one.\n<!-- PageBreak -->\nPage two."
    chunks = chunk_markdown(text=text, config=ChunkingConfig())
    assert spans(chunks) == [("Page one.\n\nPage two.", 0, len(text), None)]


def test_size_split_repeats_bounded_context() -> None:
    text = "one two\n\nthree four\n\nfive six"
    chunks = chunk_markdown(
        text=text, config=ChunkingConfig(max_characters=20, overlap_characters=10)
    )
    assert spans(chunks) == [
        ("one two\n\nthree four", 0, 19, None),
        ("three four\n\nfive six", 9, 29, None),
    ]


def test_overlap_starts_at_a_word_boundary() -> None:
    text = "one two\n\nthree four\n\nfive six"
    chunks = chunk_markdown(
        text=text, config=ChunkingConfig(max_characters=20, overlap_characters=8)
    )
    assert spans(chunks)[1] == ("four\n\nfive six", 15, 29, None)


def test_long_blocks_split_at_sentence_then_word_boundaries() -> None:
    text = "First one. Second one. Third"
    chunks = chunk_markdown(
        text=text, config=ChunkingConfig(max_characters=16, overlap_characters=0)
    )
    assert [chunk.text for chunk in chunks] == ["First one.", "Second one.", "Third"]
    unbroken = chunk_markdown(
        text="abcdefgh", config=ChunkingConfig(max_characters=3, overlap_characters=0)
    )
    assert [chunk.text for chunk in unbroken] == ["abc", "def", "gh"]


def test_blank_text_has_no_chunks() -> None:
    assert chunk_markdown(text=" \n<!-- x -->\n\t", config=ChunkingConfig()) == ()


@pytest.mark.parametrize(
    ("text", "config"),
    [(None, ChunkingConfig()), ("text", None), (b"text", ChunkingConfig())],
)
def test_invalid_input_types_fail_safely(text: object, config: object) -> None:
    with pytest.raises(RetrievalConfigurationError):
        unchecked(chunk_markdown)(text=text, config=config)


def unchecked[ResultT](function: Callable[..., ResultT]) -> Callable[..., ResultT]:
    return function
