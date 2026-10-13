import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def bash_path():
    if os.name == "nt":
        candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe"
        return str(candidate) if candidate.exists() else None
    return shutil.which("bash")


class WrapperTests(unittest.TestCase):
    def test_bash_wrapper_from_another_directory(self):
        bash = bash_path()
        if not bash:
            self.skipTest("Bash is unavailable; direct Python integration remains covered")
        environment = dict(os.environ)
        environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", "")
        with tempfile.TemporaryDirectory() as cwd:
            for command, blocked in (("git status", False), ("git reset --hard", True)):
                result = subprocess.run(
                    [bash, str(ROOT / "guard.sh")], cwd=cwd, env=environment,
                    input=json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                      "tool_input": {"command": command}}),
                    text=True, capture_output=True, timeout=15,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(bool(result.stdout.strip()), blocked)

    def test_missing_compatible_python_is_rejected(self):
        bash = bash_path()
        if not bash:
            self.skipTest("Bash is unavailable")
        # Export failing version probes instead of inserting Windows drive
        # paths into Bash's colon-delimited PATH.
        probes = (
            'python() { return 1; }; py() { return 1; }; python3() { return 1; }; '
            'export -f python py python3; bash "$1"'
        )
        result = subprocess.run(
            [bash, "-c", probes, "wrapper-test", str(ROOT / "guard.sh")],
            input="{}", text=True, capture_output=True, timeout=15,
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("Python 3.11+ is required", result.stderr)


if __name__ == "__main__":
    unittest.main()
