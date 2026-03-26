import subprocess
import unittest
from pathlib import Path
import json


ROOT_DIR = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT_DIR / "extension" / "manifest.json"
CONFIG_JS_PATH = ROOT_DIR / "extension" / "config.js"
CONTENT_JS_PATH = ROOT_DIR / "extension" / "content.js"


class ExtensionScriptTests(unittest.TestCase):
    def test_config_script_is_valid_javascript(self):
        source = CONFIG_JS_PATH.read_text(encoding="utf-8")
        self.assertIn("YOUR-PUBLIC-BACKEND.example.com/improve", source)

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

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_content_script_is_valid_javascript(self):
        source = CONTENT_JS_PATH.read_text(encoding="utf-8")

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

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_content_script_has_expected_user_facing_labels(self):
        source = CONTENT_JS_PATH.read_text(encoding="utf-8")

        self.assertIn("\\uD604\\uC7AC \\uD504\\uB86C\\uD504\\uD2B8", source)
        self.assertIn("\\uC720\\uC9C0\\uD558\\uAE30", source)
        self.assertIn("\\uAC1C\\uC120 \\uC801\\uC6A9", source)
        self.assertIn("\\uBB38\\uC81C\\uC810", source)
        self.assertIn("\\uCD94\\uCC9C \\uD504\\uB86C\\uD504\\uD2B8", source)
        self.assertIn("BETTER_PROMPT_RUNTIME_CONFIG.apiUrl", source)
        self.assertNotIn("127.0.0.1:8000/improve", source)

    def test_manifest_loads_config_before_content_script(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        content_scripts = manifest["content_scripts"][0]["js"]

        self.assertEqual(content_scripts[0], "config.js")
        self.assertEqual(content_scripts[1], "content.js")


if __name__ == "__main__":
    unittest.main()
