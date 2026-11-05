"""Run mocked regression checks without OpenAI/Google network requests.

Usage: python scripts/verify_offline.py [--dependencies PATH]
Dependencies can come from a venv or an isolated pip --target directory.
Node must be available on PATH. This is not a live Chrome or AI quality test.
"""
import argparse
import faulthandler
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr

parser = argparse.ArgumentParser()
parser.add_argument("--dependencies", type=Path)
args = parser.parse_args()
if args.dependencies:
    sys.path.insert(0, str(args.dependencies.resolve()))
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
os.chdir(root)
os.environ["OPENAI_API_KEY"] = ""
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
import httpx

blocked = []
def no_http(*args, **kwargs):
    blocked.append("real HTTP transport blocked")
    raise RuntimeError("External HTTP disabled by offline verifier")

httpx.HTTPTransport.handle_request = no_http
httpx.AsyncHTTPTransport.handle_async_request = no_http
faulthandler.dump_traceback_later(30, exit=True)
output = io.StringIO()
with redirect_stdout(output), redirect_stderr(output):
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(
        unittest.defaultTestLoader.discover(str(root / "tests"))
    )
faulthandler.cancel_dump_traceback_later()
node = subprocess.run(
    ["node", "--test", "tests/extension_runtime.test.cjs"],
    capture_output=True, encoding="utf-8", timeout=30,
)
report_dir = root / "verification"
report_dir.mkdir(exist_ok=True)
(report_dir / "python-tests.txt").write_text(output.getvalue(), encoding="utf-8")
(report_dir / "extension-tests.txt").write_text(node.stdout + node.stderr, encoding="utf-8")
summary = {
    "python_tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
    "skipped": len(result.skipped), "extension_exit_code": node.returncode,
    "blocked_real_http_attempts": len(blocked), "real_ai_calls": 0, "real_google_calls": 0,
    "cash_spend_krw": 0, "live_chrome_tested": False, "live_model_quality_tested": False,
}
(report_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))
if not result.wasSuccessful():
    print(output.getvalue())
if node.returncode:
    print(node.stdout + node.stderr)
raise SystemExit(0 if result.wasSuccessful() and node.returncode == 0 and not blocked else 1)
