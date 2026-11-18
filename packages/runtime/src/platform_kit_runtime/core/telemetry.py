"""Content-free inference tracing port and its disabled default; stdlib only."""

from contextlib import AbstractContextManager, nullcontext
from typing import Protocol

from platform_kit_runtime.core.ai import AIError, TextResult


class InferenceSpan(Protocol):
    """Records the outcome of one inference call; never prompts or completions."""

    def succeeded(self, *, result: TextResult) -> None:
        """Record token usage and the finish reason of ``result``, not its text."""
        ...

    def failed(self, *, error: AIError) -> None:
        """Record the stable code of ``error`` as the failure type."""
        ...


class InferenceTracer(Protocol):
    """Opens one span around each inference call."""

    def span(
        self, *, model: str, max_output_tokens: int
    ) -> AbstractContextManager[InferenceSpan]:
        """Start a span for one inference call and end it on exit.

        Args:
            model (str): Provider-prefixed model selector, for example
                ``azure/deployment``.
            max_output_tokens (int): Requested output token cap.

        Returns:
            AbstractContextManager[InferenceSpan]: Context yielding the span.
        """
        ...


class _SilentSpan:
    def succeeded(self, *, result: TextResult) -> None:
        """Ignore ``result``."""

    def failed(self, *, error: AIError) -> None:
        """Ignore ``error``."""


class SilentInferenceTracer:
    """Records nothing; the default when no tracer is composed."""

    def span(
        self, *, model: str, max_output_tokens: int
    ) -> AbstractContextManager[InferenceSpan]:
        """Return a context yielding a span that ignores every outcome.

        Args:
            model (str): Unused model selector.
            max_output_tokens (int): Unused output token cap.

        Returns:
            AbstractContextManager[InferenceSpan]: A no-op context.
        """
        del model, max_output_tokens
        return nullcontext(_SilentSpan())
