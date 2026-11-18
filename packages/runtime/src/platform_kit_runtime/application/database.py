"""Unit-of-work orchestration over the transactional session port."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from platform_kit_runtime.core.database import TransactionalSession


@asynccontextmanager
async def transaction[SessionT: TransactionalSession](
    *, session: SessionT
) -> AsyncGenerator[SessionT]:
    """Yield ``session``; commit when the block completes, else roll back and re-raise.

    Any exception from the block or from ``commit``, including cancellation,
    triggers one rollback before it propagates unchanged. The caller still
    owns and closes the session.
    """
    try:
        yield session
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
