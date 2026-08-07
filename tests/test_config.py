import pytest

from app.config import ConfigurationError, Settings


def test_requires_provider_and_service_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("STOCKTRACKER_API_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)

    with pytest.raises(ConfigurationError, match="GEMINI_API_KEY"):
        Settings.from_environment()


def test_loads_bounded_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret")
    monkeypatch.setenv("STOCKTRACKER_API_KEY", "service-secret")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("MAX_AGENT_STEPS", "4")
    monkeypatch.delenv("REQUEST_TIMEOUT_SECONDS", raising=False)

    settings = Settings.from_environment()

    assert settings.max_agent_steps == 4
    assert settings.stocktracker_base_url == "http://localhost:8080"
    assert settings.request_timeout_seconds == 150
    assert settings.session_cookie_name == "finscope_session"
    assert settings.session_cookie_secure is False
    assert settings.demo_username == ""
    assert settings.demo_email == "demo@finscope.tw"
