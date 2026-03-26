import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
SITE_PACKAGES = ROOT_DIR / "backend" / ".venv" / "Lib" / "site-packages"

if SITE_PACKAGES.exists():
    sys.path.insert(0, str(SITE_PACKAGES))

sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient

from backend.config import settings
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
    def setUp(self):
        self.client = TestClient(app)
        self.original_rate_limiter = backend_main._rate_limiter
        backend_main._rate_limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)

    def tearDown(self):
        backend_main._rate_limiter = self.original_rate_limiter

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


if __name__ == "__main__":
    unittest.main()
