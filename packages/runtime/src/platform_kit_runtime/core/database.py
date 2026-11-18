"""PostgreSQL connection settings, credential-free errors and ports; stdlib only."""

from dataclasses import dataclass, field
from typing import Protocol, override

from platform_kit_runtime.core.validation import is_int_in_range, is_nonblank

_DEFAULT_PORT = 5432
_MAX_PORT = 65535
_DEFAULT_POOL_SIZE = 5
_DEFAULT_MAX_OVERFLOW = 5
_MAX_POOL_CONNECTIONS = 100


class DatabaseError(Exception):
    """Base database failure with a fixed message that never contains credentials."""

    message = "Database operation failed."

    def __init__(self) -> None:
        """Construct an error without accepting connection values."""
        super().__init__(self.message)


class DatabaseConfigurationError(DatabaseError, ValueError):
    """A database setting is invalid; only the setting name is reported.

    Attributes:
        setting (str): Name of the rejected setting, never its value.
    """

    message = "Database configuration is invalid."

    def __init__(self, *, setting: str) -> None:
        """Name the rejected setting without echoing its value.

        Args:
            setting (str): Code-defined setting name, for example ``password``.
        """
        super().__init__()
        self.setting = setting

    @override
    def __str__(self) -> str:
        return f"Database setting {self.setting!r} is invalid."


class DatabaseAuthenticationError(DatabaseError):
    """The credential could not supply a database access token."""

    message = "Database access token could not be acquired."


class DatabaseAccessToken(Protocol):
    """Access token returned by a credential; only ``token`` is read."""

    @property
    def token(self) -> str:
        """Opaque bearer token used once as a connection password."""
        ...


class DatabaseTokenCredential(Protocol):
    """Async token source, such as an ``azure.identity.aio`` credential."""

    async def get_token(self, *scopes: str) -> DatabaseAccessToken:
        """Return a current access token for ``scopes``; the adapter passes one."""
        ...


class TransactionalSession(Protocol):
    """Session operations needed to finish one unit of work."""

    async def commit(self) -> None:
        """Persist the pending transaction."""
        ...

    async def rollback(self) -> None:
        """Discard the pending transaction."""
        ...


@dataclass(frozen=True, kw_only=True, slots=True)
class DatabaseSettings:
    """Explicit PostgreSQL connection settings; nothing is read from the environment.

    Attributes:
        host (str): Server host name or address, without scheme or credentials.
        database (str): Database name.
        user (str): Login role; for Entra authentication, the Entra principal
            name mapped to a database role. Omitted from repr.
        password (str | None): Password for password authentication; must be
            ``None`` with Entra authentication. Omitted from repr.
        port (int): Server TCP port.
        entra_authentication (bool): Use a fresh Microsoft Entra access token as
            the password for each new connection; requires TLS and no password.
        require_tls (bool): Require TLS with certificate and host name
            verification against the system trust store. Disable only for
            local development servers without TLS.
        pool_size (int): Connections kept open per engine, from 1 to 100.
        max_overflow (int): Extra connections opened under load, from 0 to 100.
    """

    host: str
    database: str
    user: str = field(repr=False)
    password: str | None = field(default=None, repr=False)
    port: int = _DEFAULT_PORT
    entra_authentication: bool = False
    require_tls: bool = True
    pool_size: int = _DEFAULT_POOL_SIZE
    max_overflow: int = _DEFAULT_MAX_OVERFLOW

    def __post_init__(self) -> None:
        """Validate settings before any driver import or network access.

        Raises:
            DatabaseConfigurationError: A setting is invalid; values are not echoed.
        """
        checks = (
            (
                "host",
                is_nonblank(self.host) and not any(map(str.isspace, self.host)),
            ),
            ("database", is_nonblank(self.database)),
            ("user", is_nonblank(self.user)),
            ("port", is_int_in_range(self.port, low=1, high=_MAX_PORT)),
            ("entra_authentication", isinstance(self.entra_authentication, bool)),
            ("require_tls", isinstance(self.require_tls, bool)),
            (
                "pool_size",
                is_int_in_range(self.pool_size, low=1, high=_MAX_POOL_CONNECTIONS),
            ),
            (
                "max_overflow",
                is_int_in_range(self.max_overflow, low=0, high=_MAX_POOL_CONNECTIONS),
            ),
            ("password", self._password_matches_mode()),
            ("require_tls", self.require_tls or not self.entra_authentication),
        )
        for setting, valid in checks:
            if not valid:
                raise DatabaseConfigurationError(setting=setting)

    def _password_matches_mode(self) -> bool:
        if self.entra_authentication:
            return self.password is None
        return isinstance(self.password, str) and bool(self.password)
