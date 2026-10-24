"""Configuration precedence, origin validation and safe startup failures."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings, load_settings


def test_defaults_deny_cross_origin_access() -> None:
    settings = Settings()
    assert settings.docs_enabled is True
    assert settings.database_url is None
    assert settings.cors_allowed_origins == ()


def test_dotenv_path_does_not_depend_on_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dotenv = tmp_path / "backend.env"
    dotenv.write_text('DOCS_ENABLED=false\nCORS_ALLOWED_ORIGINS=["http://localhost:3100"]\n')
    monkeypatch.setitem(Settings.model_config, "env_file", dotenv)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / ".env").write_text("DOCS_ENABLED=invalid\n")
    monkeypatch.chdir(elsewhere)

    settings = load_settings()
    assert settings.docs_enabled is False
    assert settings.cors_allowed_origins == ("http://localhost:3100",)


def test_process_environment_overrides_dotenv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dotenv = tmp_path / "backend.env"
    dotenv.write_text('DOCS_ENABLED=false\nCORS_ALLOWED_ORIGINS=["http://localhost:3000"]\n')
    monkeypatch.setitem(Settings.model_config, "env_file", dotenv)
    monkeypatch.setenv("DOCS_ENABLED", "true")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["https://recruiting.example"]')

    settings = load_settings()
    assert settings.docs_enabled is True
    assert settings.cors_allowed_origins == ("https://recruiting.example",)


def test_explicit_settings_override_process_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCS_ENABLED", "true")
    assert Settings(docs_enabled=False).docs_enabled is False


def test_normalizes_and_deduplicates_browser_origins() -> None:
    settings = Settings(
        cors_allowed_origins=(
            "HTTPS://Example.COM:443/",
            "https://example.com",
            "http://[::1]:3000",
        )
    )
    assert settings.cors_allowed_origins == ("https://example.com", "http://[::1]:3000")


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "https://*.example.com",
        "null",
        "ftp://example.com",
        "https://example.com/path",
        "https://example.com?token=private",
        "https://example.com#fragment",
        "https://user:private@example.com",
        " https://example.com",
        "https://example.com ",
        "",
    ],
)
def test_rejects_invalid_or_overbroad_origin(origin: str) -> None:
    with pytest.raises(ValidationError):
        Settings(cors_allowed_origins=(origin,))


def test_remote_origins_require_https_without_environment_modes() -> None:
    with pytest.raises(ValidationError, match="must use HTTPS"):
        Settings(cors_allowed_origins=("http://recruiting.example",))
    assert Settings(cors_allowed_origins=("http://localhost:3000",)).cors_allowed_origins


@pytest.mark.parametrize("value", ["maybe", "enabled", ""])
def test_rejects_unrecognized_docs_flag(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("DOCS_ENABLED", value)
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize(
    "name, value",
    [
        ("DOCS_ENABLED", "private-configuration-value"),
        ("CORS_ALLOWED_ORIGINS", "private-configuration-value"),
        ("CORS_ALLOWED_ORIGINS", '["https://user:private-configuration-value@example.com"]'),
    ],
)
def test_startup_errors_do_not_echo_configuration(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(RuntimeError, match="Invalid backend configuration") as caught:
        load_settings()
    assert "private-configuration-value" not in str(caught.value)
    assert caught.value.__suppress_context__ is True


def test_unknown_dotenv_key_fails_clearly(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dotenv = tmp_path / "backend.env"
    dotenv.write_text("APP_EN=production\nUNKNOWN_SECRET=private-value\n")
    monkeypatch.setitem(Settings.model_config, "env_file", dotenv)
    with pytest.raises(RuntimeError, match="Invalid backend configuration") as caught:
        load_settings()
    assert "private-value" not in str(caught.value)


def test_unreadable_dotenv_fails_safely(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dotenv = tmp_path / "backend.env"
    dotenv.write_bytes(b"DOCS_ENABLED=\xff")
    monkeypatch.setitem(Settings.model_config, "env_file", dotenv)
    with pytest.raises(RuntimeError, match="Invalid backend configuration"):
        load_settings()
