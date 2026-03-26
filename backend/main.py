import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from typing import Deque, DefaultDict, List, Tuple

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

try:
    from .config import settings
    from .providers import (
        GeminiPromptProvider,
        PromptAnalysisProvider,
        ProviderConfigError,
        ProviderRequestError,
    )
except ImportError:
    # backend 폴더에서 `uvicorn main:app`으로 실행할 때를 위한 fallback import
    from config import settings
    from providers import (
        GeminiPromptProvider,
        PromptAnalysisProvider,
        ProviderConfigError,
        ProviderRequestError,
    )


logger = logging.getLogger("better_prompt.api")


class ImproveRequest(BaseModel):
    prompt: str = Field(
        ...,
        min_length=1,
        max_length=settings.max_prompt_length,
        description=f"Original user prompt (max {settings.max_prompt_length} chars)",
    )


class Issue(BaseModel):
    # 문제 이름은 짧고 명확하게 유지한다.
    type: str = Field(..., min_length=1, max_length=60)
    # 한 줄 설명으로 제한해서 결과를 읽기 쉽게 만든다.
    description: str = Field(
        ...,
        min_length=1,
        max_length=200,
        pattern=r"^[^\r\n]+$",
    )


class ImproveResponse(BaseModel):
    # issues는 0~3개까지만 허용한다.
    issues: List[Issue] = Field(..., min_length=0, max_length=3)
    improved_prompt: str = Field(..., min_length=1)


ISSUE_TYPE_MAP = {
    "ambiguity": "모호한 표현",
    "unclear intent": "의도 불명확",
    "lack of context": "맥락 부족",
    "missing context": "맥락 부족",
    "missing constraints": "조건 부족",
    "lack of constraints": "조건 부족",
    "insufficient specificity": "구체성 부족",
    "not specific enough": "구체성 부족",
    "overly broad request": "범위 과도",
    "too broad": "범위 과도",
    "output format missing": "출력 형식 미정의",
    "missing output format": "출력 형식 미정의",
    "format mismatch": "형식 불일치",
    "role not defined": "역할 미정의",
    "audience unclear": "대상 불명확",
    "objective unclear": "목표 불명확",
}


def _normalize_issue_key(raw: str) -> str:
    return " ".join(raw.strip().lower().replace("_", " ").replace("-", " ").split())


def _contains_korean(text: str) -> bool:
    return any("가" <= ch <= "힣" for ch in text)


def localize_issue_type(raw_type: str) -> str:
    normalized = _normalize_issue_key(raw_type)
    if not normalized:
        return "문제 유형 미정"

    if _contains_korean(raw_type):
        return raw_type.strip()

    if normalized in ISSUE_TYPE_MAP:
        return ISSUE_TYPE_MAP[normalized]

    return "문제 유형 미정"


def localize_provider_error(message: str) -> str:
    lowered = message.lower()

    if "http 429" in lowered:
        return "AI 사용량이 초과되었습니다. 잠시 후 다시 시도해 주세요."

    if "http 404" in lowered and "model" in lowered:
        return "선택한 Gemini 모델을 사용할 수 없습니다. .env의 GEMINI_MODEL 값을 확인해 주세요."

    if "timeout" in lowered or "timed out" in lowered:
        return "AI 응답이 너무 느립니다. 잠시 후 다시 시도해 주세요."

    if any(code in lowered for code in ("http 500", "http 502", "http 503", "http 504")):
        return "AI 서비스가 일시적으로 불안정합니다. 잠시 후 다시 시도해 주세요."

    return "AI 응답 처리 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요."


def get_provider() -> PromptAnalysisProvider:
    """설정된 provider 구현을 반환한다."""
    if settings.provider == "gemini":
        return GeminiPromptProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            api_base=settings.gemini_api_base,
            timeout_seconds=settings.gemini_timeout_seconds,
            retry_attempts=settings.gemini_retry_attempts,
            max_output_tokens=settings.gemini_max_output_tokens,
        )

    raise ProviderConfigError(
        f"Unsupported BETTER_PROMPT_PROVIDER: '{settings.provider}'"
    )


@dataclass
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int = 0


class InMemoryRateLimiter:
    """아주 단순한 고정 창 rate limit 이다."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max(1, max_requests)
        self.window_seconds = max(1, window_seconds)
        self._events: DefaultDict[str, Deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, identifier: str, now: float | None = None) -> RateLimitResult:
        timestamp = now if now is not None else time.time()

        with self._lock:
            events = self._events[identifier]
            cutoff = timestamp - self.window_seconds
            while events and events[0] <= cutoff:
                events.popleft()

            if not events:
                self._events.pop(identifier, None)
                events = self._events[identifier]

            if len(events) >= self.max_requests:
                retry_after = int(max(1, (events[0] + self.window_seconds) - timestamp))
                return RateLimitResult(allowed=False, retry_after_seconds=retry_after)

            events.append(timestamp)
            return RateLimitResult(allowed=True)


app = FastAPI(title="Better Prompt API")

# 공개 배포에서는 허용할 출처만 최소한으로 열어 둔다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_allowed_origins),
    allow_credentials=False,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

_rate_limiter = InMemoryRateLimiter(
    max_requests=settings.rate_limit_max_requests,
    window_seconds=settings.rate_limit_window_seconds,
)


def _get_client_identifier(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or "unknown"

    if request.client and request.client.host:
        return request.client.host

    return "unknown"


@app.middleware("http")
async def request_logging_and_rate_limit(
    request: Request, call_next
):  # type: ignore[no-untyped-def]
    started_at = time.perf_counter()
    client_id = _get_client_identifier(request)

    if request.method == "POST" and request.url.path == "/improve":
        limit_result = _rate_limiter.allow(client_id)
        if not limit_result.allowed:
            logger.warning(
                "rate_limited path=%s client=%s retry_after=%s",
                request.url.path,
                client_id,
                limit_result.retry_after_seconds,
            )
            response = JSONResponse(
                status_code=429,
                content={
                    "detail": "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요."
                },
            )
            response.headers["Retry-After"] = str(limit_result.retry_after_seconds)
            return response

    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_failed path=%s client=%s", request.url.path, client_id)
        raise

    elapsed_ms = (time.perf_counter() - started_at) * 1000
    logger.info(
        "request_done method=%s path=%s status=%s client=%s duration_ms=%.1f",
        request.method,
        request.url.path,
        response.status_code,
        client_id,
        elapsed_ms,
    )
    return response


@app.post("/improve", response_model=ImproveResponse)
def improve_prompt(request: Request, payload: ImproveRequest) -> ImproveResponse:
    """프롬프트를 분석해서 구조화된 개선 결과를 반환한다."""
    try:
        provider = get_provider()
        logger.info(
            "improve_request client=%s prompt_length=%s",
            _get_client_identifier(request),
            len(payload.prompt),
        )
        result = provider.analyze_prompt(payload.prompt)

        # 타입명이 영어로 오면 한국어 카테고리로 바꿔 둔다.
        issues = result.get("issues")
        if isinstance(issues, list):
            for issue in issues:
                if isinstance(issue, dict):
                    issue["type"] = localize_issue_type(str(issue.get("type", "")))

        return ImproveResponse(**result)
    except ProviderConfigError as exc:
        raw_message = str(exc)
        if "GEMINI_API_KEY is missing" in raw_message:
            detail = "GEMINI_API_KEY가 설정되지 않았습니다. backend/.env 파일을 확인해 주세요."
        else:
            detail = "AI Provider 설정에 문제가 있습니다. 설정값을 확인해 주세요."
        raise HTTPException(status_code=500, detail=detail) from exc
    except ProviderRequestError as exc:
        raise HTTPException(
            status_code=502, detail=localize_provider_error(str(exc))
        ) from exc
    except ValidationError as exc:
        logger.warning("invalid_provider_payload error=%s", exc)
        raise HTTPException(
            status_code=502,
            detail="AI 응답 형식이 올바르지 않습니다. 잠시 후 다시 시도해 주세요.",
        ) from exc
