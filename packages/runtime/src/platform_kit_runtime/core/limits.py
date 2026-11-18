"""Single owner of limits and unit factors shared across runtime features; stdlib only."""

from typing import Final

# Deadline for one interactive provider call or retrieval query, retries included.
DEFAULT_REQUEST_TIMEOUT_SECONDS: Final[float] = 30.0
MAX_REQUEST_TIMEOUT_SECONDS: Final[float] = 300.0
# Most SDK retries one provider call may make within its deadline.
MAX_SDK_RETRIES: Final[int] = 3
MILLISECONDS_PER_SECOND: Final[int] = 1000
