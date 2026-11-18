"""Public content-free inference tracing API; importing it loads no SDKs.

HTTP server spans come from ``RuntimeConfig(tracing=True)``; these types let
callers trace inference calls through the OpenTelemetry API.
"""

from typing import Final

from platform_kit_runtime.core.telemetry import (
    InferenceSpan,
    InferenceTracer,
    SilentInferenceTracer,
)
from platform_kit_runtime.infrastructure.telemetry import OpenTelemetryInferenceTracer

__all__: Final[list[str]] = [
    "InferenceSpan",
    "InferenceTracer",
    "OpenTelemetryInferenceTracer",
    "SilentInferenceTracer",
]
