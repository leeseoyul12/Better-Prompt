import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Protocol

import httpx


class ProviderConfigError(RuntimeError):
    """필수 provider 설정이 없을 때 사용한다."""


class ProviderRequestError(RuntimeError):
    """AI provider 호출이나 응답 형식이 잘못되었을 때 사용한다."""


class PromptAnalysisProvider(Protocol):
    def analyze_prompt(self, prompt: str) -> Dict[str, Any]:
        """ImproveResponse와 맞는 dict를 반환한다."""


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


def _build_gemini_instruction(prompt: str) -> str:
    return f"""
You are a prompt-improvement assistant.
Analyze the user's prompt and return JSON only.

Rules:
1. Return exactly this JSON shape:
{{
  "issues": [
    {{"type": "string", "description": "string"}}
  ],
  "improved_prompt": "string"
}}
2. issues may contain 0 to 3 items.
3. If the original prompt is already strong and clear, return an empty issues array.
4. Keep issue descriptions to one short sentence each.
5. improved_prompt must stay practical and natural, even when only small improvement is needed.
6. Use Korean in both issues and improved_prompt.
7. Do not include markdown, explanations, or extra keys.

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

    def analyze_prompt(self, prompt: str) -> Dict[str, Any]:
        if not self.api_key:
            raise ProviderConfigError(
                "GEMINI_API_KEY is missing. Add it to your .env file."
            )

        endpoint = f"{self.api_base}/models/{self.model}:generateContent"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": _build_gemini_instruction(prompt)}],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": self.max_output_tokens,
            },
        }

        last_error: Exception | None = None
        for attempt in range(self.retry_attempts + 1):
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

                issues = parsed.get("issues")
                if isinstance(issues, list):
                    parsed["issues"] = issues[:3]

                return parsed
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
