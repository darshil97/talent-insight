"""Validate DB configuration without contacting a database or leaking secrets."""

import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.database import create_database_engine, database_url, migration_url


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+psycopg"])
def test_normalizes_postgres_driver(scheme: str) -> None:
    url = database_url(f"{scheme}://recruiter:private@ep-example.neon.tech/neondb?sslmode=require")
    assert url.drivername == "postgresql+psycopg"
    assert url.database == "neondb"


@pytest.mark.parametrize(
    "value",
    [
        "sqlite:///catalog.db",
        "postgresql://user:private@ep-example.neon.tech/neondb",
        "postgresql://user:private@ep-example.neon.tech/neondb?sslmode=disable",
        "postgresql://user:private@localhost/",
        "not-a-connection-string",
    ],
)
def test_rejects_invalid_database_urls_safely(value: str) -> None:
    with pytest.raises(ValueError) as caught:
        database_url(value)
    assert "private" not in str(caught.value)


def test_database_credentials_are_redacted_in_settings() -> None:
    value = "postgresql://user:do-not-print@ep-example.neon.tech/neondb?sslmode=require"
    settings = Settings(database_url=value)
    assert isinstance(settings.database_url, SecretStr)
    assert "do-not-print" not in repr(settings)


def test_migrations_need_direct_endpoint() -> None:
    pooled = "postgresql://user:private@ep-example-pooler.neon.tech/neondb?sslmode=require"
    direct = "postgresql://user:private@ep-example.neon.tech/neondb?sslmode=require"
    with pytest.raises(ValueError):
        migration_url(Settings(database_url=pooled))
    assert (
        migration_url(Settings(database_url=pooled, direct_database_url=direct)).host
        == "ep-example.neon.tech"
    )
    with pytest.raises(ValidationError):
        Settings(direct_database_url=pooled)
    with pytest.raises(RuntimeError, match="DIRECT_DATABASE_URL"):
        migration_url(Settings())


def test_engine_creation_is_lazy_and_bounds_the_pool() -> None:
    engine = create_database_engine("postgresql://postgres@127.0.0.1:1/catalog")
    try:
        assert engine.pool.size() == 5
        assert engine.pool.checkedout() == 0
        assert engine.hide_parameters is True
    finally:
        engine.dispose()
