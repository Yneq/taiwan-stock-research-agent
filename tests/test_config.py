import pytest

from app.config import ConfigurationError, Settings


def test_requires_provider_and_service_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("STOCKTRACKER_API_KEY", raising=False)

    with pytest.raises(ConfigurationError, match="GEMINI_API_KEY"):
        Settings.from_environment()


def test_loads_bounded_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret")
    monkeypatch.setenv("STOCKTRACKER_API_KEY", "service-secret")
    monkeypatch.setenv("MAX_AGENT_STEPS", "4")
    monkeypatch.delenv("REQUEST_TIMEOUT_SECONDS", raising=False)

    settings = Settings.from_environment()

    assert settings.max_agent_steps == 4
    assert settings.stocktracker_base_url == "http://localhost:8080"
    assert settings.request_timeout_seconds == 150
