"""Expected input failures shared across application and adapter boundaries."""


class InputTypeError(TypeError):
    """A decoded input has the wrong Python type, not an invalid value."""

    def __init__(self, *, location: str, expected: str) -> None:
        """Describe a type mismatch without including the untrusted value.

        Args:
            location (str): Safe field or document location.
            expected (str): Description of the required type.
        """
        self.location = location
        self.expected = expected
        super().__init__(f"{location} must be {expected}")


class DuplicateJsonFieldError(ValueError):
    """A JSON object repeats a field instead of defining it unambiguously."""

    def __init__(self, field: str) -> None:
        """Identify the repeated field.

        Args:
            field (str): Repeated JSON field name.
        """
        self.field = field
        super().__init__(f"duplicate JSON field '{field}'")
