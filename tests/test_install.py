"""Installation regressions use temporary projects, never agent sessions."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import install


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / "project with spaces and 'quote'"
        self.target.mkdir()

    def run_install(self, agents, dry_run=False):
        with contextlib.redirect_stdout(io.StringIO()):
            return install.install(self.target, agents, dry_run)

    def write_json(self, relative, data):
        path = self.target / relative
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_preserves_settings_and_repeated_install_has_no_duplicates(self):
        old_handler = {"type": "command", "command": "echo existing"}
        old = {"permissions": {"deny": ["Bash(example)"]}, "env": {"EXAMPLE": "value"},
               "hooks": {"Stop": [{"hooks": [old_handler]}],
                         "PreToolUse": [{"matcher": "Write", "hooks": [old_handler]}]}}
        path = self.write_json(".claude/settings.json", old)
        self.run_install(["claude", "codex"])
        first = path.read_text(encoding="utf-8")
        self.run_install(["claude", "codex"])
        self.assertEqual(path.read_text(encoding="utf-8"), first)
        merged = json.loads(first)
        self.assertEqual(merged["permissions"], old["permissions"])
        self.assertEqual(merged["env"], old["env"])
        self.assertEqual(merged["hooks"]["Stop"], old["hooks"]["Stop"])
        self.assertEqual(merged["hooks"]["PreToolUse"][0], old["hooks"]["PreToolUse"][0])
        self.assertEqual(len(merged["hooks"]["PreToolUse"]), 2)
        self.assertEqual(len(merged["hooks"]["PermissionRequest"]), 1)
        backups = list(path.parent.glob("settings.json.guard-backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(json.loads(backups[0].read_text()), old)

    def test_dry_run_writes_nothing(self):
        self.assertEqual(len(self.run_install(["claude", "codex"], True)), 5)
        self.assertEqual(list(self.target.iterdir()), [])

    def test_update_preserves_unrelated_handler_matcher(self):
        old_handler = {"type": "command", "command": "echo existing"}
        path = self.write_json(".codex/hooks.json", {"hooks": {"PreToolUse": [
            {"matcher": "Write|Bash", "hooks": [old_handler,
             {"type": "command", "command": "python .agent-guard/guard.py"}]}
        ]}})
        self.run_install(["codex"])
        groups = json.loads(path.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
        self.assertEqual(groups[0], {"matcher": "Write|Bash", "hooks": [old_handler]})
        self.assertEqual(groups[1]["matcher"], "^Bash$")

    def test_guard_path_in_unrelated_arguments_is_preserved(self):
        for agent, relative in (("claude", ".claude/settings.json"), ("codex", ".codex/hooks.json")):
            unrelated = {"type": "command", "command": "python lint.py --exclude .agent-guard/guard.py"}
            old = {"hooks": {event: [{"matcher": "Write", "hooks": [unrelated]}]
                             for event in ("PreToolUse", "PermissionRequest")}}
            path = self.write_json(relative, old)
            self.run_install([agent])
            result = json.loads(path.read_text(encoding="utf-8"))
            for event in ("PreToolUse", "PermissionRequest"):
                self.assertEqual(result["hooks"][event][0], old["hooks"][event][0])
                self.assertEqual(len(result["hooks"][event]), 2)

    def test_invalid_second_config_stops_before_writing(self):
        valid = self.write_json(".claude/settings.json", {"permissions": {}})
        invalid = self.write_json(".codex/hooks.json", {"hooks": {"PreToolUse": {}}})
        before = valid.read_bytes(), invalid.read_bytes()
        with self.assertRaises(ValueError):
            self.run_install(["claude", "codex"])
        self.assertEqual((valid.read_bytes(), invalid.read_bytes()), before)
        self.assertFalse((self.target / ".agent-guard").exists())

    def test_single_agent_does_not_create_other_settings(self):
        self.run_install(["codex"])
        self.assertFalse((self.target / ".claude").exists())
        self.assertTrue((self.target / ".codex/hooks.json").exists())

    def test_installed_commands_work_from_a_subdirectory(self):
        self.run_install(["claude", "codex"])
        cwd = self.target / "nested"
        cwd.mkdir()
        for agent, relative in (("claude", ".claude/settings.json"), ("codex", ".codex/hooks.json")):
            settings = json.loads((self.target / relative).read_text(encoding="utf-8"))
            for event in ("PreToolUse", "PermissionRequest"):
                handler = settings["hooks"][event][0]["hooks"][0]
                for command, blocked in (("git status", False), ("git reset --hard", True)):
                    payload = json.dumps({"hook_event_name": event, "tool_name": "Bash",
                                          "tool_input": {"command": command}})
                    if os.name == "nt" and agent == "claude":
                        invocation = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", handler["command"]]
                        result = subprocess.run(invocation, input=payload, text=True,
                                                capture_output=True, cwd=cwd, timeout=30)
                    else:
                        invocation = handler.get("commandWindows", handler["command"])
                        result = subprocess.run(invocation, shell=True, input=payload, text=True,
                                                capture_output=True, cwd=cwd, timeout=30)
                    with self.subTest(agent=agent, event=event, blocked=blocked):
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(bool(result.stdout.strip()), blocked, result.stdout)
                        if blocked:
                            output = json.loads(result.stdout)["hookSpecificOutput"]
                            self.assertEqual(output["hookEventName"], event)


if __name__ == "__main__":
    unittest.main()
