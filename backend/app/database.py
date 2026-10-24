"""Postgres connection helpers. Importing this module never connects or writes."""

from ipaddress import ip_address
from typing import TYPE_CHECKING

from pydantic import SecretStr
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.pool import NullPool

if TYPE_CHECKING:
    from app.config import Settings

SCHEMA = "talent_insight"
VERSION_TABLE = "talent_insight_alembic_version"


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def database_url(value: SecretStr | str, *, direct: bool = False) -> URL:
    """Normalize the driver and reject non-Postgres or insecure remote URLs."""
    raw = value.get_secret_value() if isinstance(value, SecretStr) else value
    try:
        url = make_url(raw)
        if url.drivername not in ("postgres", "postgresql", "postgresql+psycopg"):
            raise ValueError
        if not url.host or not url.database or not url.username:
            raise ValueError
        if not is_loopback(url.host) and url.query.get("sslmode") not in (
            "require",
            "verify-ca",
            "verify-full",
        ):
            raise ValueError
        if direct and "-pooler" in url.host:
            raise ValueError
        return url.set(drivername="postgresql+psycopg")
    except (ArgumentError, ValueError, TypeError):
        raise ValueError(
            "Use a PostgreSQL URL with a host, user and database; remote connections need TLS, "
            "and migrations need a direct endpoint."
        ) from None


def migration_url(settings: "Settings") -> URL:
    value = settings.direct_database_url or settings.database_url
    if value is None:
        raise RuntimeError("Configure DIRECT_DATABASE_URL before running migrations.")
    return database_url(value, direct=True)


def create_database_engine(value: SecretStr | str | URL, *, direct: bool = False) -> Engine:
    raw = value.render_as_string(hide_password=False) if isinstance(value, URL) else value
    url = database_url(raw, direct=direct)
    options = {"poolclass": NullPool} if direct else {"pool_size": 5, "max_overflow": 0}
    return create_engine(
        url,
        **options,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"connect_timeout": 10, "prepare_threshold": None},
    )
