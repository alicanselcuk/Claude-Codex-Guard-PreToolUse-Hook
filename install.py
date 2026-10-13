#!/usr/bin/env python3
"""Install the shared guard into a project without replacing its settings."""
from __future__ import annotations

import argparse
import base64
import copy
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sys
import time

SOURCE = Path(__file__).resolve().parent
GUARD_PATH = ".agent-guard/guard.py"
FILES = ("guard.py", "guard.sh", "LICENSE")


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def hook_handler(target: Path, agent: str) -> dict:
    interpreter = Path(sys.executable).resolve().as_posix()
    script = (target / GUARD_PATH).as_posix()
    posix_command = shlex.join([interpreter, script])
    handler = {"type": "command", "command": posix_command, "timeout": 10}
    if os.name == "nt":
        ps_command = f"& {ps_quote(interpreter)} {ps_quote(script)}"
        if agent == "claude":
            handler.update(command=ps_command, shell="powershell")
        else:
            # Works whether Codex launches the override through cmd or PowerShell.
            encoded = base64.b64encode(ps_command.encode("utf-16-le")).decode("ascii")
            handler["commandWindows"] = "powershell.exe -NoProfile -NonInteractive -EncodedCommand " + encoded
    if agent == "codex":
        handler["statusMessage"] = "Checking shell guard"
    return handler


def load_settings(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return data


def calls_guard(handler: dict) -> bool:
    """Recognize a direct Python call, not a reference inside unrelated args."""
    if handler.get("type") != "command" or not isinstance(handler.get("command"), str):
        return False
    try:
        words = shlex.split(handler["command"])
    except ValueError:
        return False
    if words and words[0] == "&":
        words = words[1:]
    if len(words) < 2:
        return False
    executable = words[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
    if not re.fullmatch(r"(?:python(?:\d+(?:\.\d+)*)?t?|py)(?:\.exe)?", executable):
        return False
    index = 2 if executable in {"py", "py.exe"} and words[1] == "-3" else 1
    if index >= len(words):
        return False
    script = words[index].replace("\\", "/")
    return script == GUARD_PATH or script.endswith("/" + GUARD_PATH)


def merge_settings(data: dict, handler: dict, matcher: str) -> dict:
    result = copy.deepcopy(data)
    hooks = result.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("Existing 'hooks' must be an object.")
    for event in ("PreToolUse", "PermissionRequest"):
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            raise ValueError(f"Existing {event} hooks must be an array.")
        retained = []
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                raise ValueError(f"Invalid {event} matcher group.")
            handlers = []
            for existing in group["hooks"]:
                if not isinstance(existing, dict):
                    raise ValueError(f"Invalid {event} hook handler.")
                if calls_guard(existing):
                    continue
                handlers.append(existing)
            if handlers:
                group["hooks"] = handlers
                retained.append(group)
            elif not group["hooks"]:
                retained.append(group)
        retained.append({"matcher": matcher, "hooks": [copy.deepcopy(handler)]})
        hooks[event] = retained
    return result


def install(target: Path, agents: list[str], dry_run: bool = False) -> list[Path]:
    target = target.resolve()
    if not target.is_dir():
        raise ValueError(f"Target directory does not exist: {target}")
    for name in FILES:
        if not (SOURCE / name).is_file():
            raise ValueError(f"Missing source file: {name}")
    settings = []
    # Validate every selected configuration before copying or changing anything.
    for agent in agents:
        relative = ".claude/settings.json" if agent == "claude" else ".codex/hooks.json"
        path = target / relative
        original = load_settings(path)
        matcher = "^(Bash|PowerShell)$" if agent == "claude" else "^Bash$"
        merged = merge_settings(original, hook_handler(target, agent), matcher)
        settings.append((path, original, merged))
    outputs = [target / ".agent-guard" / name for name in FILES]
    outputs.extend(path for path, _, _ in settings)
    if dry_run:
        return outputs
    destination = target / ".agent-guard"
    destination.mkdir(exist_ok=True)
    for name in FILES:
        shutil.copy2(SOURCE / name, destination / name)
    for path, original, merged in settings:
        if path.exists() and original == merged:
            continue
        path.parent.mkdir(exist_ok=True)
        if path.exists():
            backup = path.with_name(path.name + ".guard-backup-" + str(time.time_ns()))
            shutil.copy2(path, backup)
            print(f"Backup: {backup}")
        path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, type=Path, help="Existing project directory")
    parser.add_argument("--agent", choices=("claude", "codex", "both"), default="both")
    parser.add_argument("--dry-run", action="store_true", help="Validate and show paths without writing")
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        parser.error("Python 3.11+ is required")
    agents = ["claude", "codex"] if args.agent == "both" else [args.agent]
    try:
        outputs = install(args.target, agents, args.dry_run)
    except (ValueError, OSError) as exc:
        print(f"Installation stopped: {exc}", file=sys.stderr)
        return 1
    print("Would install:" if args.dry_run else "Installed:")
    for path in outputs:
        print(f"  {path}")
    if not args.dry_run:
        print("Restart the agent and inspect /hooks. Review and trust the hook in Codex.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
