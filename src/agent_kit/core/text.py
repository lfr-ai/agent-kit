"""Pure text checks shared by catalog and native-role validation."""

import re
import unicodedata

_ASCII_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ASCII_RUN = re.compile(r"[\x00-\x7f]+")
_HIDDEN_CATEGORIES = frozenset({"Cc", "Cf"})


def visible_text(value: str) -> bool:
    """Reject control and format characters other than tab, newline and return.

    ASCII is checked with one compiled pattern; only the non-ASCII remainder is
    classified character by character, because format characters ('Cf') are
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
