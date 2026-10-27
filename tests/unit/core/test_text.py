"""Behavior of the dependency-free text checks used by source validation."""

import unicodedata

from hypothesis import given, settings
from hypothesis import strategies as st
import pytest

from agent_kit.core.text import markdown_link_targets, visible_text


def _reference(value: str) -> bool:
    """Classify every character, as the original implementation did."""
    return all(
        character in "\t\n\r" or unicodedata.category(character) not in {"Cc", "Cf"}
        for character in value
    )


@pytest.mark.parametrize(
    "value",
    ["", "plain ascii", "tab\tnewline\nreturn\r", "åäö 日本語 emoji 🚀", "e\u0301"],
)
def test_visible_text_accepts_ordinary_text(value: str) -> None:
    """Printable text, whitespace separators, and combining marks are visible."""
    assert visible_text(value)


@pytest.mark.parametrize(
    "value",
    [
        "\x00",
        "bell\x07",
        "escape\x1b[0m",
        "delete\x7f",
        "zero\u200bwidth",
        "bidi\u202eoverride",
        "joiner\u200d",
        "bom\ufeff",
        "tag\U000e0041",
        "ascii then \u00ad soft hyphen",
        "C1 control \x85",
    ],
)
def test_visible_text_rejects_hidden_controls_and_format_characters(
    value: str,
) -> None:
    """Control and format characters can hide instructions from reviewers."""
    assert not visible_text(value)


@given(st.text())
@settings(max_examples=300, database=None, derandomize=True)
def test_visible_text_matches_the_character_classification(value: str) -> None:
    """The ASCII fast path never changes which text is accepted."""
    assert visible_text(value) is _reference(value)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("[a](one.md) and ![i](two.png)", ["one.md", "two.png"]),
        ("[a](<spaced name.md>)", ["spaced name.md"]),
        ("[a]( padded.md )", ["padded.md"]),
        ("[no target]()", []),
        ("plain text without links", []),
    ],
)
def test_markdown_link_targets_reads_inline_links(
    text: str, expected: list[str]
) -> None:
    """Inline links and images are returned without angle brackets."""
    assert list(markdown_link_targets(text)) == expected


@pytest.mark.parametrize("fence", ["```", "~~~", "   ```", "````"])
def test_markdown_link_targets_ignores_fenced_code(fence: str) -> None:
    """Example links inside code fences are not resource references."""
    text = f"[real](a.md)\n{fence}\n[example](missing.md)\n{fence}\n[after](b.md)\n"
    assert list(markdown_link_targets(text)) == ["a.md", "b.md"]


def test_markdown_link_targets_ignores_an_unclosed_fence_to_the_end() -> None:
    """An unclosed fence hides the rest of the document, as in CommonMark."""
    text = "[real](a.md)\n```\n[hidden](b.md)\n"
    assert list(markdown_link_targets(text)) == ["a.md"]


def test_markdown_link_targets_requires_a_matching_closing_fence() -> None:
    """A shorter or different fence marker does not close the block."""
    text = "````\n[x](hidden.md)\n```\n[y](hidden.md)\n````\n[z](shown.md)\n"
    assert list(markdown_link_targets(text)) == ["shown.md"]
