import os
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from dotenv import load_dotenv


# backend/.env를 고정 경로로 읽어서 실행 환경 차이를 줄인다.
ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)


def _parse_csv_env(name: str, default: str) -> Tuple[str, ...]:
    raw_value = os.getenv(name, default).strip()
    if not raw_value:
        return tuple()

    return tuple(item.strip() for item in raw_value.split(",") if item.strip())


def _parse_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        return int(raw_value)
    except ValueError:
        return default


def _parse_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        return float(raw_value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # provider 이름은 새 이름을 우선 사용하고, 예전 이름도 함께 허용한다.
    provider: str = os.getenv(
        "BETTER_PROMPT_PROVIDER",
        os.getenv("PROMPT_COACH_PROVIDER", "gemini"),
    ).strip().lower()
    # Google AI Studio?쒖꽌 諛쒓툒??API Key濡?Gemini Developer API瑜??몄텧?쒕떎.
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip()
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    gemini_api_base: str = os.getenv(
        "GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta"
    ).strip()
    gemini_timeout_seconds: float = _parse_float_env("GEMINI_TIMEOUT_SECONDS", 20.0)
    gemini_retry_attempts: int = _parse_int_env("GEMINI_RETRY_ATTEMPTS", 1)
    gemini_max_output_tokens: int = _parse_int_env("GEMINI_MAX_OUTPUT_TOKENS", 512)
    max_prompt_length: int = _parse_int_env("BETTER_PROMPT_MAX_PROMPT_LENGTH", 2000)
    saved_prompt_max_length: int = _parse_int_env(
        "BETTER_PROMPT_SAVED_PROMPT_MAX_LENGTH", 6000
    )
    rate_limit_max_requests: int = _parse_int_env(
        "BETTER_PROMPT_RATE_LIMIT_MAX_REQUESTS", 10
    )
    rate_limit_window_seconds: int = _parse_int_env(
        "BETTER_PROMPT_RATE_LIMIT_WINDOW_SECONDS", 60
    )
    database_url: str = os.getenv(
        "BETTER_PROMPT_DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/better_prompt",
    ).strip()
    session_duration_days: int = _parse_int_env("BETTER_PROMPT_SESSION_DURATION_DAYS", 14)
    google_userinfo_url: str = os.getenv(
        "BETTER_PROMPT_GOOGLE_USERINFO_URL",
        "https://www.googleapis.com/oauth2/v3/userinfo",
    ).strip()
    cors_allowed_origins: Tuple[str, ...] = _parse_csv_env(
        "BETTER_PROMPT_ALLOWED_ORIGINS",
        "https://chatgpt.com,https://chat.openai.com",
    )


settings = Settings()
