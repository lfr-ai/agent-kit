"""Deliberately unversioned health routes, without business endpoints."""

from dataclasses import dataclass
from enum import StrEnum, auto, unique

from fastapi import APIRouter, FastAPI, Response

from platform_kit_runtime.application.readiness import ReadinessService


@unique
class HealthStatus(StrEnum):
    """Closed successful health response values."""

    OK = auto()
    READY = auto()


@dataclass(frozen=True, kw_only=True, slots=True)
class HealthResponse:
    """Public health body containing only the supplied status.

    Attributes:
        status (HealthStatus): Closed successful health result.
    """

    status: HealthStatus


def install_health_routes(*, app: FastAPI, readiness: ReadinessService) -> None:
    """Bind health routes to the supplied readiness use case.

    Args:
        app (FastAPI): Owning application receiving the health router.
        readiness (ReadinessService): Consumer-probe orchestration for readiness.
    """
    router = APIRouter(prefix="/health")

    @router.get("/live", operation_id="getLiveness")
    async def live(*, response: Response) -> HealthResponse:
        response.headers["Cache-Control"] = "no-store"
        return HealthResponse(status=HealthStatus.OK)

    @router.get("/ready", operation_id="getReadiness")
    async def ready(*, response: Response) -> HealthResponse:
        await readiness.check()
        response.headers["Cache-Control"] = "no-store"
        return HealthResponse(status=HealthStatus.READY)

    app.include_router(router)
