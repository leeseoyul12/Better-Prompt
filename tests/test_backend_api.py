import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
SITE_PACKAGES = ROOT_DIR / "backend" / ".venv" / "Lib" / "site-packages"
TEST_DB_PATH = ROOT_DIR / "tests" / "test_app.sqlite3"

os.environ["BETTER_PROMPT_DATABASE_URL"] = "sqlite:///" + TEST_DB_PATH.as_posix()

if SITE_PACKAGES.exists():
    sys.path.insert(0, str(SITE_PACKAGES))

sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient

from backend.auth import GoogleProfile
from backend.config import settings
from backend.database import SavedPrompt, SessionLocal, User, UserSession, init_database
from backend.main import InMemoryRateLimiter, app
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

        with SessionLocal() as db:
            db.query(UserSession).delete()
            db.query(SavedPrompt).delete()
            db.query(User).delete()
            db.commit()

    def tearDown(self):
        backend_main._rate_limiter = self.original_rate_limiter

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
