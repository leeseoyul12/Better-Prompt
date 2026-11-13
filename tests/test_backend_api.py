import os
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
SITE_PACKAGES = ROOT_DIR / "backend" / ".venv" / "Lib" / "site-packages"
_TEST_DB_DIRECTORY = tempfile.TemporaryDirectory(prefix="better-prompt-test-")
TEST_DB_PATH = Path(_TEST_DB_DIRECTORY.name) / "test_app.sqlite3"

os.environ["BETTER_PROMPT_DATABASE_URL"] = "sqlite:///" + TEST_DB_PATH.as_posix()

if SITE_PACKAGES.exists():
    sys.path.insert(0, str(SITE_PACKAGES))

sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient

from backend.auth import GoogleProfile
from backend.config import settings
from backend.database import SavedPrompt, SessionLocal, User, UserSession, engine, init_database
from backend.main import InMemoryRateLimiter, app
from backend.providers import OpenAIPromptProvider, ProviderRequestError
import backend.main as backend_main


class _ValidProvider:
    def analyze_prompt(self, prompt: str):
        return {
            "issues": [
                {"type": "ambiguity", "description": "Needs clearer scope."},
                {"type": "missing constraints", "description": "Needs explicit constraints."},
            ],
            "improved_prompt": f"Improved prompt: {prompt}",
        }


class _InvalidProvider:
    def analyze_prompt(self, prompt: str):
        return {
            "issues": "not-a-list",
            "improved_prompt": "",
        }


class ImproveApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()
        init_database()

    def setUp(self):
        self.client = TestClient(app)
        self.original_rate_limiter = backend_main._rate_limiter
        backend_main._rate_limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
        # Most tests exercise the existing API behavior independently of the
        # invite gate; dedicated tests below exercise real session + allowlist.
        app.dependency_overrides[backend_main.get_improve_user] = lambda: None

        with SessionLocal() as db:
            db.query(UserSession).delete()
            db.query(SavedPrompt).delete()
            db.query(User).delete()
            db.commit()

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()
        backend_main._rate_limiter = self.original_rate_limiter

    @classmethod
    def tearDownClass(cls):
        engine.dispose()
        _TEST_DB_DIRECTORY.cleanup()

    def _login(self, sub: str, email: str, display_name: str = "Tester") -> str:
        with patch(
            "backend.auth.GoogleIdentityService.fetch_profile",
            return_value=GoogleProfile(sub=sub, email=email, name=display_name),
        ):
            response = self.client.post("/auth/google", json={"access_token": "google-token"})

        self.assertEqual(response.status_code, 200)
        return response.json()["session_token"]

    def test_improve_returns_expected_schema(self):
        with patch("backend.main.get_provider", return_value=_ValidProvider()):
            response = self.client.post("/improve", json={"prompt": "draft prompt"})

        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("issues", data)
        self.assertIn("improved_prompt", data)
        self.assertLessEqual(len(data["issues"]), 3)
        self.assertTrue(data["issues"][0]["type"])
        self.assertTrue(data["issues"][0]["description"])
        self.assertTrue(data["improved_prompt"])

    def test_improve_rejects_invalid_provider_payload(self):
        with patch("backend.main.get_provider", return_value=_InvalidProvider()):
            response = self.client.post("/improve", json={"prompt": "draft prompt"})

        self.assertEqual(response.status_code, 502)
        self.assertIn("detail", response.json())

    def test_improve_rejects_overlong_prompt(self):
        long_prompt = "a" * (settings.max_prompt_length + 1)

        with patch("backend.main.get_provider", return_value=_ValidProvider()):
            response = self.client.post("/improve", json={"prompt": long_prompt})

        self.assertEqual(response.status_code, 422)
        self.assertIn("detail", response.json())

    def test_health_does_not_call_model_or_query_database(self):
        with patch("backend.main.get_provider", side_effect=AssertionError("AI called")), patch(
            "backend.main.SessionLocal", side_effect=AssertionError("Database queried")
        ):
            response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_blank_prompt_is_rejected_before_provider_call(self):
        with patch("backend.main.get_provider") as provider:
            response = self.client.post("/improve", json={"prompt": " \n\t "})
        self.assertEqual(response.status_code, 422)
        provider.assert_not_called()

    def test_real_provider_malformed_model_result_returns_error_not_success(self):
        from unittest.mock import Mock
        provider = OpenAIPromptProvider("fake-key", "gpt-5-mini", "https://example.invalid/v1")
        response = Mock()
        response.json.return_value = {"output_text": "not JSON"}
        with patch("backend.main.get_provider", return_value=provider), patch(
            "backend.providers.httpx.post", return_value=response
        ) as post:
            result = self.client.post("/improve", json={"prompt": "작업 요청을 명확하게 바꿔 줘"})
        self.assertEqual(result.status_code, 502)
        self.assertIn("detail", result.json())
        self.assertNotIn("improved_prompt", result.json())
        post.assert_called_once()

    def test_provider_timeout_becomes_localized_error(self):
        with patch("backend.main.get_provider") as get_provider:
            get_provider.return_value.analyze_prompt.side_effect = ProviderRequestError("OpenAI timeout")
            response = self.client.post("/improve", json={"prompt": "원래 요청"})
        self.assertEqual(response.status_code, 502)
        self.assertIn("느립니다", response.json()["detail"])

    def test_anonymous_improvement_never_calls_provider(self):
        app.dependency_overrides.clear()
        with patch("backend.main.get_provider") as provider:
            result = self.client.post("/improve", json={"prompt": "이 코드를 설명해 줘"})
        self.assertEqual(result.status_code, 401)
        provider.assert_not_called()

    def test_invited_session_can_improve(self):
        app.dependency_overrides.clear()
        token = self._login("invited-sub", "invited@example.com")
        with patch("backend.main.settings", replace(settings, improve_allowed_emails=("invited@example.com",))), patch(
            "backend.main.get_provider", return_value=_ValidProvider()
        ):
            result = self.client.post("/improve", json={"prompt": "이 코드를 설명해 줘"},
                                      headers={"Authorization": "Bearer " + token})
        self.assertEqual(result.status_code, 200)

    def test_noninvited_session_never_calls_provider(self):
        app.dependency_overrides.clear()
        token = self._login("other-sub", "other@example.com")
        with patch("backend.main.settings", replace(settings, improve_allowed_emails=("invited@example.com",))), patch(
            "backend.main.get_provider"
        ) as provider:
            result = self.client.post("/improve", json={"prompt": "이 코드를 설명해 줘"},
                                      headers={"Authorization": "Bearer " + token})
        self.assertEqual(result.status_code, 403)
        provider.assert_not_called()

    def test_empty_invite_list_denies_everyone(self):
        app.dependency_overrides.clear()
        token = self._login("empty-list-sub", "invited@example.com")
        with patch("backend.main.settings", replace(settings, improve_allowed_emails=())), patch(
            "backend.main.get_provider"
        ) as provider:
            result = self.client.post("/improve", json={"prompt": "이 코드를 설명해 줘"},
                                      headers={"Authorization": "Bearer " + token})
        self.assertEqual(result.status_code, 403)
        provider.assert_not_called()

    def test_public_improvement_checks_account_and_service_limits_before_model(self):
        app.dependency_overrides.clear()
        first = self._login("public-first", "first@example.com")
        second = self._login("public-second", "second@example.com")
        third = self._login("public-third", "third@example.com")
        with (
            patch("backend.main.settings", replace(settings, improve_public_access=True)),
            patch("backend.main._rate_limiter", InMemoryRateLimiter(20, 60)),
            patch("backend.main._public_user_limiter", InMemoryRateLimiter(1, 3600)),
            patch("backend.main._public_service_limiter", InMemoryRateLimiter(2, 3600)),
            patch("backend.main.get_provider", return_value=_ValidProvider()) as provider,
        ):
            responses = [
                self.client.post("/improve", json={"prompt": "회의 안내문을 다듬어 줘"},
                                 headers={"Authorization": f"Bearer {token}"})
                for token in (first, first, second, third)
            ]
        self.assertEqual([response.status_code for response in responses], [200, 429, 200, 429])
        self.assertIn("계정당", responses[1].json()["detail"])
        self.assertIn("서비스", responses[3].json()["detail"])
        self.assertIn("Retry-After", responses[3].headers)
        self.assertEqual(provider.call_count, 2)

    def test_improve_rate_limits_repeated_requests(self):
        with patch("backend.main.get_provider", return_value=_ValidProvider()):
            first_response = self.client.post("/improve", json={"prompt": "draft prompt"})
            second_response = self.client.post("/improve", json={"prompt": "draft prompt"})

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 429)
        self.assertIn("Retry-After", second_response.headers)

    def test_google_auth_returns_service_session_and_me_endpoint(self):
        session_token = self._login("google-sub-1", "user1@example.com", "User One")

        response = self.client.get(
            "/me",
            headers={"Authorization": f"Bearer {session_token}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["email"], "user1@example.com")

    def test_logout_invalidates_current_session(self):
        session_token = self._login("google-sub-logout", "logout@example.com")

        logout_response = self.client.post(
            "/auth/logout",
            headers={"Authorization": f"Bearer {session_token}"},
        )
        me_response = self.client.get(
            "/me",
            headers={"Authorization": f"Bearer {session_token}"},
        )

        self.assertEqual(logout_response.status_code, 200)
        self.assertEqual(me_response.status_code, 401)

    def test_saved_prompt_crud_and_latest_first_order(self):
        session_token = self._login("google-sub-2", "user2@example.com")
        headers = {"Authorization": f"Bearer {session_token}"}

        first_response = self.client.post(
            "/saved-prompts",
            headers=headers,
            json={"title": "첫 번째", "content": "첫 번째 프롬프트"},
        )
        second_response = self.client.post(
            "/saved-prompts",
            headers=headers,
            json={"title": "두 번째", "content": "두 번째 프롬프트"},
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)

        saved_prompt_id = first_response.json()["id"]
        patch_response = self.client.patch(
            f"/saved-prompts/{saved_prompt_id}",
            headers=headers,
            json={"title": "수정된 첫 번째"},
        )
        list_response = self.client.get("/saved-prompts", headers=headers)
        delete_response = self.client.delete(
            f"/saved-prompts/{saved_prompt_id}",
            headers=headers,
        )

        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(list_response.json()[0]["title"], "수정된 첫 번째")

    def test_saved_prompt_data_is_isolated_per_user(self):
        session_token_user1 = self._login("google-sub-3", "user3@example.com")
        session_token_user2 = self._login("google-sub-4", "user4@example.com")

        create_response = self.client.post(
            "/saved-prompts",
            headers={"Authorization": f"Bearer {session_token_user1}"},
            json={"title": "개인 프롬프트", "content": "비공개 내용"},
        )
        saved_prompt_id = create_response.json()["id"]

        list_response = self.client.get(
            "/saved-prompts",
            headers={"Authorization": f"Bearer {session_token_user2}"},
        )
        patch_response = self.client.patch(
            f"/saved-prompts/{saved_prompt_id}",
            headers={"Authorization": f"Bearer {session_token_user2}"},
            json={"title": "침범 시도"},
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json(), [])
        self.assertEqual(patch_response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
