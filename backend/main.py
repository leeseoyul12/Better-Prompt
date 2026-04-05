import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Deque, DefaultDict, List

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import (
    AuthenticationError,
    authenticate_google_access_token,
    get_user_for_session_token,
    revoke_session_token,
)
from .config import settings
from .database import SavedPrompt, SessionLocal, User, init_database
from .providers import (
    OpenAIPromptProvider,
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
    # 문제 이름은 짧고 명확한 단어로 유지한다.
    type: str = Field(..., min_length=1, max_length=60)
    # 한 줄 설명만 허용해 팝업 UI에서 바로 읽히게 만든다.
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


class GoogleAuthRequest(BaseModel):
    access_token: str = Field(..., min_length=1, max_length=4096)


class UserResponse(BaseModel):
    id: int
    email: str
    display_name: str


class GoogleAuthResponse(BaseModel):
    session_token: str
    user: UserResponse


class MeResponse(BaseModel):
    user: UserResponse


class SavedPromptCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    content: str = Field(
        ...,
        min_length=1,
        max_length=settings.saved_prompt_max_length,
    )


class SavedPromptUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    content: str | None = Field(
        default=None,
        min_length=1,
        max_length=settings.saved_prompt_max_length,
    )


class SavedPromptResponse(BaseModel):
    id: int
    title: str
    content: str
    created_at: datetime
    updated_at: datetime


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
    "output format missing": "출력 형식 미지정",
    "missing output format": "출력 형식 미지정",
    "format mismatch": "형식 불일치",
    "role not defined": "역할 미지정",
    "audience unclear": "대상 불명확",
    "objective unclear": "목표 불명확",
}


def _normalize_issue_key(raw: str) -> str:
    return " ".join(raw.strip().lower().replace("_", " ").replace("-", " ").split())


def _contains_korean(text: str) -> bool:
    return any("\uac00" <= ch <= "\ud7a3" for ch in text)


def localize_issue_type(raw_type: str) -> str:
    normalized = _normalize_issue_key(raw_type)
    if not normalized:
        return "문제 유형 미지정"

    if _contains_korean(raw_type):
        return raw_type.strip()

    if normalized in ISSUE_TYPE_MAP:
        return ISSUE_TYPE_MAP[normalized]

    return "문제 유형 미지정"


def localize_provider_error(message: str) -> str:
    lowered = message.lower()

    if "http 429" in lowered:
        return "AI 사용량이 초과됐습니다. 잠시 후 다시 시도해 주세요."

    if "http 404" in lowered and "model" in lowered:
        return "선택한 OpenAI 모델을 사용할 수 없습니다. .env의 OPENAI_MODEL 값을 확인해 주세요."

    if "timeout" in lowered or "timed out" in lowered:
        return "AI 응답이 너무 느립니다. 잠시 후 다시 시도해 주세요."

    if any(code in lowered for code in ("http 500", "http 502", "http 503", "http 504")):
        return "AI 서비스가 일시적으로 불안정합니다. 잠시 후 다시 시도해 주세요."

    return "AI 응답 처리 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요."


def get_provider() -> PromptAnalysisProvider:
    """설정된 provider 구현체를 반환한다."""
    if settings.provider == "openai":
        return OpenAIPromptProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            api_base=settings.openai_api_base,
            timeout_seconds=settings.openai_timeout_seconds,
            retry_attempts=settings.openai_retry_attempts,
            max_output_tokens=settings.openai_max_output_tokens,
        )

    raise ProviderConfigError(
        f"Unsupported BETTER_PROMPT_PROVIDER: '{settings.provider}'"
    )


@dataclass
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int = 0


class InMemoryRateLimiter:
    """아주 단순한 고정 창 rate limit이다."""

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

# 확장 프로그램이 Authorization 헤더를 써야 하므로 허용 메서드와 헤더를 넓혀둔다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_allowed_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

_rate_limiter = InMemoryRateLimiter(
    max_requests=settings.rate_limit_max_requests,
    window_seconds=settings.rate_limit_window_seconds,
)


@app.on_event("startup")
def on_startup() -> None:
    init_database()


def _get_client_identifier(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or "unknown"

    if request.client and request.client.host:
        return request.client.host

    return "unknown"


def _to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
    )


def _to_saved_prompt_response(saved_prompt: SavedPrompt) -> SavedPromptResponse:
    return SavedPromptResponse(
        id=saved_prompt.id,
        title=saved_prompt.title,
        content=saved_prompt.content,
        created_at=saved_prompt.created_at,
        updated_at=saved_prompt.updated_at,
    )


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    prefix = "bearer "
    lowered = authorization.lower()
    if not lowered.startswith(prefix):
        raise HTTPException(status_code=401, detail="올바른 인증 토큰 형식이 아닙니다.")

    token = authorization[len(prefix) :].strip()
    if not token:
        raise HTTPException(status_code=401, detail="인증 토큰이 비어 있습니다.")

    return token


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    token = _extract_bearer_token(authorization)

    try:
        return get_user_for_session_token(db, token)
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail="로그인 세션이 만료됐습니다.") from exc


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
                content={"detail": "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요."},
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

        issues = result.get("issues")
        if isinstance(issues, list):
            for issue in issues:
                if isinstance(issue, dict):
                    issue["type"] = localize_issue_type(str(issue.get("type", "")))

        return ImproveResponse(**result)
    except ProviderConfigError as exc:
        raw_message = str(exc)
        if "OPENAI_API_KEY is missing" in raw_message:
            detail = "OPENAI_API_KEY가 설정되지 않았습니다. backend/.env 파일을 확인해 주세요."
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


@app.post("/auth/google", response_model=GoogleAuthResponse)
def authenticate_google(
    payload: GoogleAuthRequest,
    db: Session = Depends(get_db),
) -> GoogleAuthResponse:
    """구글 access token을 검증하고 서비스 세션을 발급한다."""
    try:
        session = authenticate_google_access_token(db, payload.access_token)
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail="구글 로그인 검증에 실패했습니다.") from exc

    return GoogleAuthResponse(
        session_token=session.session_token,
        user=_to_user_response(session.user),
    )


@app.post("/auth/logout")
def logout(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """현재 서비스 세션을 종료한다."""
    token = _extract_bearer_token(authorization)
    revoke_session_token(db, token)
    return {"detail": "로그아웃되었습니다."}


@app.get("/me", response_model=MeResponse)
def me(current_user: User = Depends(get_current_user)) -> MeResponse:
    """현재 로그인 사용자 정보를 반환한다."""
    return MeResponse(user=_to_user_response(current_user))


@app.get("/saved-prompts", response_model=list[SavedPromptResponse])
def list_saved_prompts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SavedPromptResponse]:
    """현재 사용자의 저장 프롬프트 목록을 최신순으로 반환한다."""
    saved_prompts = db.scalars(
        select(SavedPrompt)
        .where(SavedPrompt.user_id == current_user.id)
        .order_by(SavedPrompt.updated_at.desc(), SavedPrompt.id.desc())
    ).all()
    return [_to_saved_prompt_response(item) for item in saved_prompts]


@app.post("/saved-prompts", response_model=SavedPromptResponse)
def create_saved_prompt(
    payload: SavedPromptCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SavedPromptResponse:
    """개선된 프롬프트를 제목과 함께 저장한다."""
    saved_prompt = SavedPrompt(
        user_id=current_user.id,
        title=payload.title.strip(),
        content=payload.content.strip(),
    )
    db.add(saved_prompt)
    db.commit()
    db.refresh(saved_prompt)
    return _to_saved_prompt_response(saved_prompt)


@app.patch("/saved-prompts/{saved_prompt_id}", response_model=SavedPromptResponse)
def update_saved_prompt(
    saved_prompt_id: int,
    payload: SavedPromptUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SavedPromptResponse:
    """저장된 프롬프트의 제목 또는 본문을 수정한다."""
    if payload.title is None and payload.content is None:
        raise HTTPException(status_code=400, detail="수정할 값이 없습니다.")

    saved_prompt = db.scalar(
        select(SavedPrompt).where(
            SavedPrompt.id == saved_prompt_id,
            SavedPrompt.user_id == current_user.id,
        )
    )
    if saved_prompt is None:
        raise HTTPException(status_code=404, detail="저장된 프롬프트를 찾을 수 없습니다.")

    if payload.title is not None:
        saved_prompt.title = payload.title.strip()
    if payload.content is not None:
        saved_prompt.content = payload.content.strip()

    db.commit()
    db.refresh(saved_prompt)
    return _to_saved_prompt_response(saved_prompt)


@app.delete("/saved-prompts/{saved_prompt_id}")
def delete_saved_prompt(
    saved_prompt_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """현재 사용자의 저장 프롬프트를 삭제한다."""
    saved_prompt = db.scalar(
        select(SavedPrompt).where(
            SavedPrompt.id == saved_prompt_id,
            SavedPrompt.user_id == current_user.id,
        )
    )
    if saved_prompt is None:
        raise HTTPException(status_code=404, detail="저장된 프롬프트를 찾을 수 없습니다.")

    db.delete(saved_prompt)
    db.commit()
    return {"detail": "저장된 프롬프트를 삭제했습니다."}
