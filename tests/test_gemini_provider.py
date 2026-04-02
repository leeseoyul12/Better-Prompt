import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT_DIR = Path(__file__).resolve().parents[1]
SITE_PACKAGES = ROOT_DIR / "backend" / ".venv" / "Lib" / "site-packages"

if SITE_PACKAGES.exists():
    sys.path.insert(0, str(SITE_PACKAGES))

sys.path.insert(0, str(ROOT_DIR))

from backend.providers import GeminiPromptProvider, ProviderConfigError


class GeminiProviderTests(unittest.TestCase):
    def test_gemini_provider_calls_developer_api_with_api_key(self):
        provider = GeminiPromptProvider(
            api_key="test-api-key",
            model="gemini-2.5-flash",
            api_base="https://generativelanguage.googleapis.com/v1beta",
            timeout_seconds=12.5,
            retry_attempts=0,
            max_output_tokens=256,
        )

        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    '{"issues":[{"type":"모호한 표현","description":"범위를 더 '
                                    '분명히 하면 좋습니다."}],"improved_prompt":"개선된 프롬프트"}'
                                )
                            }
                        ]
                    }
                }
            ]
        }

        with patch("backend.providers.httpx.post", return_value=response) as mocked_post:
            result = provider.analyze_prompt("초안 프롬프트")

        self.assertEqual(result["improved_prompt"], "개선된 프롬프트")
        self.assertEqual(len(result["issues"]), 1)

        mocked_post.assert_called_once()
        args, kwargs = mocked_post.call_args
        self.assertEqual(
            args[0],
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
        )
        self.assertEqual(kwargs["params"], {"key": "test-api-key"})
        self.assertEqual(kwargs["timeout"], 12.5)
        self.assertEqual(kwargs["json"]["generationConfig"]["maxOutputTokens"], 256)
        self.assertNotIn("headers", kwargs)

    def test_gemini_provider_requires_api_key(self):
        provider = GeminiPromptProvider(
            api_key="",
            model="gemini-2.5-flash",
            api_base="https://generativelanguage.googleapis.com/v1beta",
        )

        with self.assertRaises(ProviderConfigError):
            provider.analyze_prompt("초안 프롬프트")

    def test_env_example_uses_new_default_model(self):
        env_example = (ROOT_DIR / "backend" / ".env.example").read_text(encoding="utf-8")

        self.assertIn("GEMINI_MODEL=gemini-2.5-flash", env_example)
        self.assertIn(
            "GEMINI_API_BASE=https://generativelanguage.googleapis.com/v1beta",
            env_example,
        )


if __name__ == "__main__":
    unittest.main()
