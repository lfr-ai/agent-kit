"""FastAPI dependency providing one database session per request."""

from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager


def session_dependency[SessionT](
    *, sessions: Callable[[], AbstractAsyncContextManager[SessionT]]
) -> Callable[[], AsyncGenerator[SessionT]]:
    """Return a ``Depends`` dependency yielding one session from ``sessions``.

    ``sessions`` is a session factory such as an ``async_sessionmaker``. The
    session is not committed automatically; wrap writes in ``transaction``.
    FastAPI closes it when the dependency scope ends, by default after the
    response is sent.
    """

    async def provide_session() -> AsyncGenerator[SessionT]:
        async with sessions() as session:
            yield session

    return provide_session
