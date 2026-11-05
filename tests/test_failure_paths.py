import json
import unittest
from unittest.mock import Mock, patch

import httpx

from backend.providers import OpenAIPromptProvider, ProviderRequestError


def response(payload):
    result = Mock()
    result.json.return_value = payload
    return result


def analysis(text, issues=None):
    return {"output_text": json.dumps({"issues": issues or [], "improved_prompt": text})}


class ProviderFailureTests(unittest.TestCase):
    def setUp(self):
        self.provider = OpenAIPromptProvider("fake-key", "gpt-5-mini", "https://example.invalid/v1")

    def test_invalid_result_types_never_masquerade_as_success(self):
        for parsed in [[], {}, {"issues": [], "improved_prompt": None},
                       {"issues": [], "improved_prompt": 123},
                       {"issues": "wrong", "improved_prompt": "요청문"},
                       {"issues": [None], "improved_prompt": "요청문"},
                       {"issues": [{"type": "x", "description": 123}], "improved_prompt": "요청문"}]:
            with self.subTest(parsed=parsed), patch("backend.providers.httpx.post", return_value=response(
                {"output_text": json.dumps(parsed)}
            )) as post:
                with self.assertRaises(ProviderRequestError):
                    self.provider.analyze_prompt("사용자의 요청")
                post.assert_called_once()

    def test_incomplete_refused_or_empty_response_is_failure(self):
        for payload in [[], {"status": "incomplete", **analysis("중간에 끊긴 요청문")},
                        {"output": [{"content": [{"type": "refusal", "refusal": "Refused"}]}]},
                        {"output_text": ""}]:
            with self.subTest(payload=payload), patch("backend.providers.httpx.post", return_value=response(payload)):
                with self.assertRaises(ProviderRequestError):
                    self.provider.analyze_prompt("사용자의 요청")

    def test_first_person_context_is_not_mistaken_for_assistant_answer(self):
        text = "저는 학생입니다.\n아래 코드를 설명해 주세요.\n```python\nprint('hi')\n```"
        with patch("backend.providers.httpx.post", return_value=response(analysis(text))):
            result = self.provider.analyze_prompt("저는 학생입니다. 이 코드를 설명해주세요")
        self.assertEqual(result["improved_prompt"], text)

    def test_original_self_description_is_allowed(self):
        text = "저는 AI입니다. 이 문장을 영어로 번역해 주세요."
        with patch("backend.providers.httpx.post", return_value=response(analysis(text))):
            self.assertEqual(self.provider.analyze_prompt(text)["improved_prompt"], text)

    def test_ai_student_context_is_not_assistant_self_introduction(self):
        for text in ["저는 AI를 배우는 학생입니다. 이 코드를 설명해 주세요.",
                     "I am an AI researcher. Explain this code."]:
            with self.subTest(text=text), patch("backend.providers.httpx.post", return_value=response(analysis(text))):
                result = self.provider.analyze_prompt("학생에게 코드를 설명해 주세요")
            self.assertEqual(result["improved_prompt"], text)

    def test_default_does_not_retry_timeout(self):
        with patch("backend.providers.httpx.post", side_effect=httpx.ReadTimeout("timeout")) as post:
            with self.assertRaises(ProviderRequestError):
                self.provider.analyze_prompt("사용자의 요청")
        post.assert_called_once()

    def test_legacy_retry_ten_is_capped_at_one_retry(self):
        self.provider.retry_attempts = 10
        request = httpx.Request("POST", "https://example.invalid/v1/responses")
        failed = httpx.Response(503, request=request)
        exc = httpx.HTTPStatusError("unavailable", request=request, response=failed)
        with patch("backend.providers.httpx.post", side_effect=exc) as post, patch("backend.providers.time.sleep"):
            with self.assertRaises(ProviderRequestError):
                self.provider.analyze_prompt("사용자의 요청")
        self.assertEqual(post.call_count, 2)

    def test_auth_error_is_not_retried_and_does_not_log_prompt_or_body(self):
        self.provider.retry_attempts = 1
        request = httpx.Request("POST", "https://example.invalid/v1/responses")
        failed = httpx.Response(401, request=request, text="private-provider-body")
        exc = httpx.HTTPStatusError("private-error", request=request, response=failed)
        with patch("backend.providers.httpx.post", side_effect=exc) as post, self.assertLogs(
            "better_prompt.provider", level="WARNING"
        ) as logs:
            with self.assertRaises(ProviderRequestError):
                self.provider.analyze_prompt("private-user-prompt")
        post.assert_called_once()
        self.assertNotIn("private", " ".join(logs.output))

    def test_greeting_is_noop_even_without_api_key(self):
        self.provider.api_key = ""
        with patch("backend.providers.httpx.post") as post:
            self.assertEqual(self.provider.analyze_prompt("안녕하세요!")["improved_prompt"], "안녕하세요!")
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
