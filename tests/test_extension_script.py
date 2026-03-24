import subprocess
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
CONTENT_JS_PATH = ROOT_DIR / "extension" / "content.js"


class ExtensionScriptTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
