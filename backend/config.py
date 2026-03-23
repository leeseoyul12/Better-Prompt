import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


# backend 폴더의 .env를 고정 경로로 읽어 실행 위치에 영향받지 않게 한다.
ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)


@dataclass(frozen=True)
class Settings:
    # 새 이름을 우선 사용하고, 기존 이름도 잠깐 호환해 바로 깨지지 않게 한다.
    provider: str = os.getenv(
        "BETTER_PROMPT_PROVIDER",
        os.getenv("PROMPT_COACH_PROVIDER", "gemini"),
    ).strip().lower()
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip()
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()
    gemini_api_base: str = os.getenv(
        "GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta"
    ).strip()


settings = Settings()
