"""Render strict portable agent role assets into runtime-owned adapters."""

from typing import Final

from agent_kit.application.native_delivery.errors import (
    DuplicateRoleError,
    InvalidNativeJSONError,
    InvalidWorkerTargetError,
    MissingNativeFieldError,
    NativeRoleError,
    NativeRoleIssue,
    NativeRuntimeError,
    NativeTextLimitError,
    UnavailableWorkerError,
    UnknownNativeFieldError,
)
from agent_kit.application.native_delivery.rendering import render_native_agents
from agent_kit.application.native_delivery.validation import validate_native_assets

__all__: Final[list[str]] = [
    "DuplicateRoleError",
    "InvalidNativeJSONError",
    "InvalidWorkerTargetError",
    "MissingNativeFieldError",
    "NativeRoleError",
    "NativeRoleIssue",
    "NativeRuntimeError",
    "NativeTextLimitError",
    "UnavailableWorkerError",
    "UnknownNativeFieldError",
    "render_native_agents",
    "validate_native_assets",
]
