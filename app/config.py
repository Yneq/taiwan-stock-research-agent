from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


load_dotenv()


class ConfigurationError(RuntimeError):
    """Raised when a required environment variable is missing."""


@dataclass(frozen=True, slots=True)
class Settings:
    gemini_api_key: str
    gemini_model: str
    stocktracker_base_url: str
    stocktracker_api_key: str
    jwt_secret: str
    session_cookie_name: str
    session_cookie_secure: bool
    max_agent_steps: int
    request_timeout_seconds: float

    @classmethod
    def from_environment(cls) -> "Settings":
        gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        stocktracker_api_key = os.getenv("STOCKTRACKER_API_KEY", "").strip()
        jwt_secret = os.getenv("JWT_SECRET", "").strip()
        if not gemini_api_key:
            raise ConfigurationError("GEMINI_API_KEY is required")
        if not stocktracker_api_key:
            raise ConfigurationError("STOCKTRACKER_API_KEY is required")
        if len(jwt_secret) < 32:
            raise ConfigurationError("JWT_SECRET must contain at least 32 characters")

        max_steps = int(os.getenv("MAX_AGENT_STEPS", "3"))
        if max_steps < 1 or max_steps > 5:
            raise ConfigurationError("MAX_AGENT_STEPS must be between 1 and 5")

        return cls(
            gemini_api_key=gemini_api_key,
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip(),
            stocktracker_base_url=os.getenv(
                "STOCKTRACKER_BASE_URL", "http://localhost:8080"
            ).rstrip("/"),
            stocktracker_api_key=stocktracker_api_key,
            jwt_secret=jwt_secret,
            session_cookie_name=os.getenv(
                "SESSION_COOKIE_NAME", "finscope_session"
            ).strip(),
            session_cookie_secure=os.getenv(
                "SESSION_COOKIE_SECURE", "false"
            ).strip().lower()
            in {"1", "true", "yes", "on"},
            max_agent_steps=max_steps,
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "150")),
        )


@lru_cache
def get_settings() -> Settings:
    return Settings.from_environment()
