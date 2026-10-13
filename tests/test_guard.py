"""Policy regressions. Command strings are data and are never executed."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import guard

DENIED = [
    "git push --force origin main", "git push -f origin main",
    "git push --force-with-lease origin main", "git reset --hard HEAD~1",
    "git checkout .", "git checkout -- .", "git restore .",
    "git restore -- .", "git restore ./src", "git restore --staged -- .",
    "git clean -fd", "git clean -fdx", "git clean -ffdx", "git clean -fxd",
    "git branch -D old-branch", "git stash", "git stash push -m 'wip'",
    "git stash save", "git stash -u", "git stash drop stash@{0}", "git stash clear",
    "rm -rf /", "rm -rf /opt/example", "rm -f -r /tmp/cache", "rm -fr /tmp/cache",
    'rm -rf "/tmp/cache"', "rm -fr .git", "rm --force --recursive /tmp/cache",
    "rm --recursive --force /tmp/cache", "rm -rf .", "rm -rf ./src",
    "rm -rf *", "rm -rf ~", "rm -rf $HOME/projects", "rm -rf .git",
    "rm -rf .git/objects", "rm -rf .env", "rm -rf .env.local",
    "rmdir /s /q .", "rd /s /q *", "Remove-Item -Recurse .",
    "Remove-Item -Recurse C:\\", "Remove-Item -Recurse *",
    "shred -uvz private.key", "mkfs.ext4 /dev/sdb1", "format C:",
    "npx prisma migrate reset --force", 'psql -c "DROP TABLE users;"',
    'psql -c "DROP DATABASE example;"', "docker system prune -a --volumes",
    "docker volume rm database-data", "docker compose down -v",
    "docker-compose down --volumes", "chmod 777 file", "chmod -R 777 directory",
    "taskkill /F /IM codex.exe", "taskkill //F //IM claude.exe",
    "pkill -f codex", "killall -9 claude", "Stop-Process -Name codex",
    "Get-Process claude | Stop-Process",
    "git status && git push --force", 'git commit -m "fix" && git reset --hard',
    'git commit -m "$(rm -rf /)"', 'git commit -m "`rm -rf /`"',
    'rg "$(rm -rf /)" README.md', 'rg -n "rm -rf /" README.md && git reset --hard',
    "rg 'safe' README.md & bash -c 'git reset --hard'",
    "git commit -m 'safe' & bash -c 'git reset --hard'",
    "git grep --open-files-in-pager='git reset --hard; #' pattern",
    "git grep -O'git reset --hard; #' pattern",
    "rg --pre 'git reset --hard' pattern README.md",
    'bash -c "rm -rf /"', "ssh example-host 'rm -rf /opt/example'",
    "docker run --rm app sh -c 'rm -rf /opt/example'",
    "docker compose run --rm app sh -c 'rm -rf .git'",
    "docker run --rm app true && docker volume rm database-data",
    "git commit -m \"ok\" && bash <<'EOF'\nrm -rf /\nEOF",
    "git commit -m \"$(cat <<'EOF'\nok\nEOF\nrm -rf /\n)\"",
    "git commit -m \"$(cat <<'EOF'\nok\nEOF\nrm -rf /\nEOF\n)\"",
]
ALLOWED = [
    "git status", "git diff", "git push origin main", "git clean -n",
    "git branch -d merged-branch", "git checkout main", "git checkout -b feature/example",
    "git restore src/file.py", "git restore .gitignore", "git stash list",
    "git stash show -p", "git stash pop", "git stash apply", "git stash branch recovered",
    "git rm -rf old-folder", "git rm -rf /opt/example", "rm -rf .next", "rm -rf .vscode", "rm -rf .gitignore",
    "rm --force /tmp/file", "rm -f /tmp/file", "rm -rf build-cache",
    "rm -rf .envrc", "chmod 755 script.sh", "chmod -R 755 docs",
    "npx prisma db push", "npx prisma db execute --file patch.sql",
    "npx prisma migrate dev --name example", 'grep -r "pattern" src',
    'rg -n "git reset --hard|rm -rf /|DROP TABLE" README.md',
    "rg -n 'git push --force' README.md",
    "& rg 'git reset --hard' README.md",
    'git grep -n "git reset --hard|docker compose down -v" -- .',
    'git grep -o "git reset --hard" -- .',
    "git grep -Oless pattern", "rg --pre cat pattern README.md",
    'Select-String -Path README.md -Pattern "git reset --hard|rm -rf /"',
    'findstr "git reset --hard" README.md',
    'git commit -m "docs: explain git reset --hard and rm -rf /"',
    "git commit --message='docs: explain DROP TABLE'",
    "git commit -m \"$(cat <<'EOF'\ndocs: rm -rf /\nEOF\n)\"",
    'docker run --rm app true', "docker compose run --rm app true",
    "docker run --rm app sh -c 'find /app -type f'",
    "docker compose up -d", "docker compose down", "taskkill /F /PID 1234",
    "Stop-Process -Id 1234", "codex --version", "claude --version",
]


def invoke(raw: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(Path(guard.__file__))], input=raw,
        text=True, capture_output=True, timeout=10,
    )


class GuardTests(unittest.TestCase):
    def test_denied_policy(self):
        for command in DENIED:
            with self.subTest(command=command):
                self.assertIsNotNone(guard.check_command(command))

    def test_allowed_policy(self):
        for command in ALLOWED:
            with self.subTest(command=command):
                self.assertIsNone(guard.check_command(command))

    def test_shared_decisions_and_event_formats(self):
        for event in ("PreToolUse", "PermissionRequest"):
            for tool in ("Bash", "PowerShell"):
                for command, blocked in (("git reset --hard", True), ("git status", False)):
                    with self.subTest(event=event, tool=tool, blocked=blocked):
                        result = invoke(json.dumps({"hook_event_name": event, "tool_name": tool,
                                                    "tool_input": {"command": command}}))
                        self.assertEqual(result.returncode, 0, result.stderr)
                        if not blocked:
                            self.assertEqual(result.stdout, "")
                            continue
                        output = json.loads(result.stdout)["hookSpecificOutput"]
                        self.assertEqual(output["hookEventName"], event)
                        if event == "PermissionRequest":
                            self.assertEqual(output["decision"]["behavior"], "deny")
                            self.assertTrue(output["decision"]["message"])
                        else:
                            self.assertEqual(output["permissionDecision"], "deny")
                            self.assertTrue(output["permissionDecisionReason"])

    def test_non_shell_tools_are_ignored(self):
        for tool in ("Write", "Edit", "apply_patch", "mcp__example__search"):
            result = invoke(json.dumps({"tool_name": tool,
                                        "tool_input": {"command": "git reset --hard"}}))
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")

    def test_invalid_input_is_rejected(self):
        for raw in ("", "not-json", "[]", "null", '{"hook_event_name":[]}',
                    '{"hook_event_name":{}}',
                    '{"tool_name":"Bash","tool_input":null}',
                    '{"tool_name":"Bash","tool_input":{"command":123}}'):
            with self.subTest(raw=raw):
                result = invoke(raw)
                self.assertEqual(result.returncode, 2)
                self.assertIn("[guard] Invalid hook input", result.stderr)


if __name__ == "__main__":
    unittest.main()
