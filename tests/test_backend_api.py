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

from backend.main import app


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
            "issues": [
                {"type": "problem", "description": "desc 1"},
                {"type": "problem", "description": "desc 2"},
                {"type": "problem", "description": "desc 3"},
                {"type": "problem", "description": "desc 4"},
            ],
            "improved_prompt": "",
        }


class ImproveApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

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


if __name__ == "__main__":
    unittest.main()
