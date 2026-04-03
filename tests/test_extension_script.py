import json
import subprocess
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT_DIR / "extension" / "manifest.json"
CONFIG_JS_PATH = ROOT_DIR / "extension" / "config.js"
CONTENT_JS_PATH = ROOT_DIR / "extension" / "content.js"
BACKGROUND_JS_PATH = ROOT_DIR / "extension" / "background.js"


def _assert_valid_javascript(test_case: unittest.TestCase, source: str) -> None:
    result = subprocess.run(
        [
            "node",
            "-e",
            "const fs=require('fs'); const src=fs.readFileSync(0,'utf8'); new Function(src);"
        ],
        input=source,
        text=True,
        encoding="utf-8",
        capture_output=True,
        cwd=ROOT_DIR,
        check=False,
    )

    test_case.assertEqual(result.returncode, 0, result.stderr)


class ExtensionScriptTests(unittest.TestCase):
    def test_config_script_is_valid_javascript(self):
        source = CONFIG_JS_PATH.read_text(encoding="utf-8")
        self.assertIn('apiUrl: "https://', source)
        self.assertIn('/improve"', source)
        self.assertIn('googleClientId: "YOUR_GOOGLE_CLIENT_ID', source)
        _assert_valid_javascript(self, source)

    def test_content_script_is_valid_javascript(self):
        source = CONTENT_JS_PATH.read_text(encoding="utf-8")
        _assert_valid_javascript(self, source)

    def test_background_script_is_valid_javascript(self):
        source = BACKGROUND_JS_PATH.read_text(encoding="utf-8")
        self.assertIn("better-prompt-google-sign-in", source)
        _assert_valid_javascript(self, source)

    def test_content_script_has_expected_user_facing_labels(self):
        source = CONTENT_JS_PATH.read_text(encoding="utf-8")

        self.assertIn("현재 프롬프트", source)
        self.assertIn("유지하기", source)
        self.assertIn("개선 적용", source)
        self.assertIn("문제점", source)
        self.assertIn("추천 프롬프트", source)
        self.assertIn("구글 로그인", source)
        self.assertIn("저장", source)
        self.assertIn("불러오기", source)
        self.assertIn("getImproveApiUrl()", source)
        self.assertNotIn("127.0.0.1:8000/improve", source)

    def test_manifest_loads_config_before_content_script_and_registers_worker(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        content_scripts = manifest["content_scripts"][0]["js"]

        self.assertEqual(content_scripts[0], "config.js")
        self.assertEqual(content_scripts[1], "content.js")
        self.assertEqual(manifest["background"]["service_worker"], "background.js")
        self.assertIn("storage", manifest["permissions"])
        self.assertIn("identity", manifest["permissions"])


if __name__ == "__main__":
    unittest.main()
