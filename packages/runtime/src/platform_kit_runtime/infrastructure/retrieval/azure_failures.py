"""Content-free classification of Azure SDK exceptions."""

from azure.core.exceptions import (
    ClientAuthenticationError,
    HttpResponseError,
    ServiceRequestError,
    ServiceResponseError,
)

from platform_kit_runtime.infrastructure.retrieval.failures import (
    FailureKind,
    classify_status,
)


def classify_azure_failure(error: Exception) -> FailureKind:
    """Classify an SDK or deadline exception without reading its message."""
    if isinstance(error, ClientAuthenticationError):
        return FailureKind.AUTHENTICATION
    if isinstance(error, TimeoutError | ServiceRequestError | ServiceResponseError):
        return FailureKind.UNAVAILABLE
    if isinstance(error, HttpResponseError):
        return classify_status(error.status_code)
    return FailureKind.PROTOCOL
