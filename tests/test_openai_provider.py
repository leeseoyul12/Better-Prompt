import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT_DIR = Path(__file__).resolve().parents[1]
SITE_PACKAGES = ROOT_DIR / "backend" / ".venv" / "Lib" / "site-packages"

if SITE_PACKAGES.exists():
    sys.path.insert(0, str(SITE_PACKAGES))

sys.path.insert(0, str(ROOT_DIR))

from backend.providers import OpenAIPromptProvider, ProviderConfigError


def _mock_openai_response(text: str) -> Mock:
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "output": [
            {
                "content": [
                    {
                        "type": "output_text",
                        "text": text,
                    }
                ]
            }
        ],
        "output_text": text,
    }
    return response


class OpenAIProviderTests(unittest.TestCase):
    def test_openai_provider_calls_responses_api_with_bearer_token(self):
        provider = OpenAIPromptProvider(
            api_key="test-api-key",
            model="gpt-5-mini",
            api_base="https://api.openai.com/v1",
            timeout_seconds=12.5,
            retry_attempts=0,
            max_output_tokens=768,
        )

        response = _mock_openai_response(
            '{"issues":[{"type":"모호한 표현","description":"범위를 조금 더 분명히 하면 좋아요."}],"improved_prompt":"개선된 프롬프트"}'
        )

        with patch("backend.providers.httpx.post", return_value=response) as mocked_post:
            result = provider.analyze_prompt("초안 프롬프트")

        self.assertEqual(result["improved_prompt"], "개선된 프롬프트")
        self.assertEqual(len(result["issues"]), 1)

        mocked_post.assert_called_once()
        args, kwargs = mocked_post.call_args
        self.assertEqual(args[0], "https://api.openai.com/v1/responses")
        self.assertEqual(kwargs["timeout"], 12.5)
        self.assertEqual(kwargs["json"]["max_output_tokens"], 768)
        self.assertEqual(kwargs["json"]["text"]["format"]["type"], "json_schema")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-api-key")

    def test_openai_provider_requires_api_key(self):
        provider = OpenAIPromptProvider(
            api_key="",
            model="gpt-5-mini",
            api_base="https://api.openai.com/v1",
        )

        with self.assertRaises(ProviderConfigError):
            provider.analyze_prompt("초안 프롬프트")

    def test_openai_provider_falls_back_when_model_answers_instead_of_rewriting(self):
        provider = OpenAIPromptProvider(
            api_key="test-api-key",
            model="gpt-5-mini",
            api_base="https://api.openai.com/v1",
            retry_attempts=0,
        )

        response = _mock_openai_response(
            '{"issues":[{"type":"clarity","description":"질문 형태를 유지해 주세요."}],"improved_prompt":"저는 사용자의 질문에 답하는 AI입니다."}'
        )

        with patch("backend.providers.httpx.post", return_value=response):
            result = provider.analyze_prompt("넌 뭐하는 ai냐")

        self.assertEqual(result["improved_prompt"], "넌 뭐하는 ai냐?")

    def test_openai_provider_keeps_short_greeting_minimal_without_api_call(self):
        provider = OpenAIPromptProvider(
            api_key="test-api-key",
            model="gpt-5-mini",
            api_base="https://api.openai.com/v1",
            retry_attempts=0,
        )

        with patch("backend.providers.httpx.post") as mocked_post:
            result = provider.analyze_prompt("안녕")

        self.assertEqual(result["improved_prompt"], "안녕")
        mocked_post.assert_not_called()

    def test_openai_provider_returns_local_fallback_when_model_breaks_json(self):
        provider = OpenAIPromptProvider(
            api_key="test-api-key",
            model="gpt-5-mini",
            api_base="https://api.openai.com/v1",
            retry_attempts=0,
        )

        response = _mock_openai_response(
            "이 문장은 조금 더 구체적으로 쓰면 좋아요.\n개선된 프롬프트: 자바 공부를 잘할 수 있게 알려줘"
        )

        with patch("backend.providers.httpx.post", return_value=response):
            result = provider.analyze_prompt("자바 공부 어떻게 해?")

        self.assertIn("단계별로 알려줘", result["improved_prompt"])
        self.assertEqual(result["issues"], [])

    def test_env_example_uses_openai_defaults(self):
        env_example = (ROOT_DIR / "backend" / ".env.example").read_text(encoding="utf-8")

        self.assertIn("BETTER_PROMPT_PROVIDER=openai", env_example)
        self.assertIn("OPENAI_MODEL=gpt-5-mini", env_example)
        self.assertIn("OPENAI_API_BASE=https://api.openai.com/v1", env_example)
        self.assertIn("BETTER_PROMPT_DATABASE_URL=", env_example)
        self.assertIn("BETTER_PROMPT_SESSION_DURATION_DAYS=14", env_example)


if __name__ == "__main__":
    unittest.main()
