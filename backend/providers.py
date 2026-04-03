import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Protocol

import httpx


SHORT_PROMPT_CHAR_LIMIT = 12
CASUAL_KEYWORDS = (
    "안녕",
    "고마워",
    "감사",
    "반가",
    "ㅎㅎ",
    "ㅋㅋ",
    "하이",
    "hello",
    "hi",
    "thanks",
    "thank you",
)
IDENTITY_QUESTION_KEYWORDS = (
    "넌 뭐하는 ai",
    "너는 뭐하는 ai",
    "너 뭐하는 ai",
    "너는 누구",
    "넌 누구",
    "what are you",
    "who are you",
    "what do you do",
)
TASK_HINT_KEYWORDS = (
    "알려줘",
    "설명",
    "정리",
    "추천",
    "계획",
    "공부",
    "작성",
    "써줘",
    "해줘",
    "요약",
    "분석",
    "코드",
    "글",
    "문제",
    "plan",
    "write",
    "summarize",
    "explain",
    "code",
)
ANSWER_PREFIXES = (
    "안녕하세요",
    "무엇을 도와",
    "도와드릴",
    "저는 ",
    "제가 ",
    "알겠습니다",
    "좋습니다",
    "물론",
    "다음은",
    "아래는",
)


class ProviderConfigError(RuntimeError):
    """필수 provider 설정이 없을 때 사용한다."""


class ProviderRequestError(RuntimeError):
    """AI provider 호출 또는 응답 형식이 잘못됐을 때 사용한다."""


class PromptAnalysisProvider(Protocol):
    def analyze_prompt(self, prompt: str) -> Dict[str, Any]:
        """ImproveResponse에 맞는 dict를 반환한다."""


def _normalize_space(text: str) -> str:
    return " ".join(str(text).strip().split())


def _strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    return cleaned


def _extract_json_candidate(text: str) -> str:
    cleaned = _strip_code_fence(text)
    if cleaned.startswith("{") and cleaned.endswith("}"):
        return cleaned

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return cleaned[start : end + 1]

    return cleaned


def _extract_text_from_gemini(payload: Dict[str, Any]) -> str:
    candidates: List[Dict[str, Any]] = payload.get("candidates", [])
    if not candidates:
        return ""

    first_candidate = candidates[0]
    content = first_candidate.get("content", {})
    parts = content.get("parts", [])
    if not parts:
        return ""

    text_parts = [part.get("text", "") for part in parts if isinstance(part, dict)]
    return "\n".join(part for part in text_parts if part).strip()


def _is_short_prompt(prompt: str) -> bool:
    normalized = _normalize_space(prompt)
    if not normalized:
        return True
    if len(normalized) <= SHORT_PROMPT_CHAR_LIMIT:
        return True
    return len(normalized.split()) <= 3


def _looks_casual(prompt: str) -> bool:
    lowered = _normalize_space(prompt).lower()
    return any(keyword in lowered for keyword in CASUAL_KEYWORDS)


def _looks_identity_question(prompt: str) -> bool:
    lowered = _normalize_space(prompt).lower()
    return any(keyword in lowered for keyword in IDENTITY_QUESTION_KEYWORDS)


def _looks_like_task_request(prompt: str) -> bool:
    lowered = _normalize_space(prompt).lower()
    return any(keyword in lowered for keyword in TASK_HINT_KEYWORDS)


def _classify_prompt(prompt: str) -> str:
    if _looks_casual(prompt) and _is_short_prompt(prompt):
        return "casual_short"
    if _looks_identity_question(prompt):
        return "chatty_question"
    if _looks_like_task_request(prompt):
        return "task_request"
    if _is_short_prompt(prompt):
        return "short_general"
    return "task_request"


def _minimal_prompt_rewrite(prompt: str) -> str:
    normalized = _normalize_space(prompt)
    if not normalized:
        return ""

    if _looks_identity_question(normalized):
        if normalized.endswith("?"):
            return normalized
        return normalized + "?"

    if normalized[-1] in ".!?":
        return normalized

    return normalized


def _looks_like_direct_answer(original_prompt: str, candidate: str) -> bool:
    normalized_candidate = _normalize_space(candidate)
    if not normalized_candidate:
        return False

    lowered_candidate = normalized_candidate.lower()
    if any(lowered_candidate.startswith(prefix) for prefix in ANSWER_PREFIXES):
        return True

    if _looks_identity_question(original_prompt):
        if lowered_candidate.startswith("저는 ") or "대규모 언어 모델" in normalized_candidate:
            return True

    if _looks_casual(original_prompt):
        if "도와드릴" in normalized_candidate or "무엇을 도와" in normalized_candidate:
            return True

    return False


def _is_over_expanded(original_prompt: str, candidate: str) -> bool:
    normalized_original = _normalize_space(original_prompt)
    normalized_candidate = _normalize_space(candidate)

    if not normalized_original or not normalized_candidate:
        return False

    original_length = len(normalized_original)
    candidate_length = len(normalized_candidate)
    classification = _classify_prompt(original_prompt)

    if classification != "task_request" and candidate_length > max(original_length * 2, original_length + 20):
        return True

    if _is_short_prompt(original_prompt) and ("\n" in candidate or candidate_length > max(original_length + 8, 24)):
        return True

    return False


def _sanitize_issues(raw_issues: Any) -> List[Dict[str, str]]:
    if not isinstance(raw_issues, list):
        return []

    sanitized: List[Dict[str, str]] = []
    for issue in raw_issues[:3]:
        if not isinstance(issue, dict):
            continue

        issue_type = _normalize_space(issue.get("type", ""))
        description = _normalize_space(issue.get("description", ""))
        if not issue_type or not description:
            continue

        sanitized.append({"type": issue_type[:60], "description": description[:200]})

    return sanitized


def _sanitize_analysis_result(prompt: str, parsed: Dict[str, Any]) -> Dict[str, Any]:
    issues = _sanitize_issues(parsed.get("issues"))
    improved_prompt = _normalize_space(parsed.get("improved_prompt", ""))

    if not improved_prompt:
        improved_prompt = _minimal_prompt_rewrite(prompt)

    if _looks_like_direct_answer(prompt, improved_prompt):
        improved_prompt = _minimal_prompt_rewrite(prompt)
        issues = issues[:1]

    if _is_over_expanded(prompt, improved_prompt):
        improved_prompt = _minimal_prompt_rewrite(prompt)

    if not improved_prompt:
        improved_prompt = _normalize_space(prompt)

    return {
        "issues": issues,
        "improved_prompt": improved_prompt,
    }


def _build_gemini_instruction(prompt: str, strict_retry: bool = False) -> str:
    retry_rules = ""
    if strict_retry:
        retry_rules = """
Additional correction rules for this retry:
- Your previous output looked like an answer. Fix that mistake now.
- Return a rewritten prompt, not a reply to the user.
- If you are unsure, keep the original wording with only minimal cleanup.
""".strip()

    return f"""
You are not a chatbot. You are a prompt optimization engine.
Your only job is to rewrite the user's input into a better prompt.
Never answer the user's request directly.
Return JSON only.

Rules:
1. Return exactly this JSON shape:
{{
  "issues": [
    {{"type": "string", "description": "string"}}
  ],
  "improved_prompt": "string"
}}
2. issues may contain 0 to 3 items.
3. Use Korean in both issues and improved_prompt.
4. Never add markdown, explanations, greetings, or extra keys.
5. Do not invent missing facts, context, or constraints.
6. Do not change the user's intent.
7. If the prompt is already fine, keep it unchanged or make only a tiny edit.
8. For short casual inputs like greetings, do not force structure and do not make them much longer.
9. For short identity or chatty questions, keep them as questions to the AI. Do not answer them.
10. Only add structure for clear task requests, and only add what truly improves output quality.
11. If the input is 12 characters or fewer, keep the result to a single short sentence.
12. Avoid making the rewritten prompt more than about twice as long as the original unless the original is clearly a task request that benefits from structure.
13. improved_prompt must always be a prompt the user can send to an AI immediately.

Processing steps:
- First classify the input as one of: casual_short, chatty_question, task_request.
- Then rewrite according to the matching rule set.

Examples:
- Input: "안녕"
  Output improved_prompt: "안녕"
- Input: "넌 뭐하는 ai냐"
  Output improved_prompt: "너는 어떤 AI인지 간단히 소개해 줘."
- Input: "자바 공부 어떻게 해?"
  Output improved_prompt: "자바를 처음 배우는 사람 기준으로 4주 학습 계획을 단계별로 알려줘."

{retry_rules}

User prompt:
{prompt}
""".strip()


def _is_retryable_status(status_code: int) -> bool:
    return status_code in {500, 502, 503, 504}


@dataclass
class GeminiPromptProvider:
    api_key: str
    model: str
    api_base: str
    timeout_seconds: float = 20.0
    retry_attempts: int = 1
    max_output_tokens: int = 512

    def _build_payload(self, prompt: str, strict_retry: bool = False) -> Dict[str, Any]:
        return {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": _build_gemini_instruction(prompt, strict_retry=strict_retry)}],
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": self.max_output_tokens,
            },
        }

    def analyze_prompt(self, prompt: str) -> Dict[str, Any]:
        if not self.api_key:
            raise ProviderConfigError(
                "GEMINI_API_KEY is missing. Add it to your .env file."
            )

        endpoint = f"{self.api_base}/models/{self.model}:generateContent"
        last_error: Exception | None = None

        for attempt in range(self.retry_attempts + 1):
            strict_retry = attempt > 0
            payload = self._build_payload(prompt, strict_retry=strict_retry)

            try:
                response = httpx.post(
                    endpoint,
                    params={"key": self.api_key},
                    json=payload,
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()

                try:
                    response_payload = response.json()
                except ValueError as exc:
                    raise ProviderRequestError(
                        "Gemini API response was not valid JSON."
                    ) from exc

                raw_text = _extract_text_from_gemini(response_payload)
                if not raw_text:
                    raise ProviderRequestError("Gemini API response did not contain text.")

                cleaned_text = _extract_json_candidate(raw_text)
                try:
                    parsed = json.loads(cleaned_text)
                except json.JSONDecodeError as exc:
                    raise ProviderRequestError(
                        "Gemini response was not valid JSON in expected schema."
                    ) from exc

                if not isinstance(parsed, dict):
                    raise ProviderRequestError(
                        "Gemini response JSON root must be an object."
                    )

                raw_improved_prompt = str(parsed.get("improved_prompt", "")).strip()
                if attempt < self.retry_attempts and _looks_like_direct_answer(prompt, raw_improved_prompt):
                    time.sleep(min(0.3 * (attempt + 1), 1.0))
                    continue

                return _sanitize_analysis_result(prompt, parsed)
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if _is_retryable_status(exc.response.status_code) and attempt < self.retry_attempts:
                    time.sleep(min(0.5 * (attempt + 1), 1.5))
                    continue

                error_body = exc.response.text[:300]
                raise ProviderRequestError(
                    f"Gemini API returned HTTP {exc.response.status_code}: {error_body}"
                ) from exc
            except httpx.RequestError as exc:
                last_error = exc
                if attempt < self.retry_attempts:
                    time.sleep(min(0.5 * (attempt + 1), 1.5))
                    continue

                raise ProviderRequestError(
                    "Failed to call Gemini API. Check network and API endpoint settings."
                ) from exc

        if last_error is not None:
            raise ProviderRequestError("Gemini API request failed unexpectedly.") from last_error

        raise ProviderRequestError("Gemini API request failed unexpectedly.")
