"""Portable path spelling shared by publication and provenance validation."""

import ntpath


def is_relative_file_path(value: str) -> bool:
    """Recognize canonical relative file paths portable to Windows and POSIX."""
    if "\\" in value or ":" in value:
        return False
    # Path normalization would erase empty and dot segments before validation.
    return all(
        part not in {"", ".", ".."} and not ntpath.isreserved(part)
        for part in value.split("/")
    )
