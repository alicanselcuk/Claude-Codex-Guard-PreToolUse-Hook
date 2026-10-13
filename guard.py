#!/usr/bin/env python3
"""Shared shell-command policy for Claude Code and Codex lifecycle hooks.

Reads JSON on stdin. A match emits an explicit deny decision; no match emits
nothing and leaves the agent's normal permission checks in place.
"""
from __future__ import annotations

import json
import re
import sys
from typing import Any

if sys.version_info < (3, 11):
    print("[guard] Python 3.11 or newer is required.", file=sys.stderr)
    raise SystemExit(2)

DENY_REASON = (
    "Guard blocked a potentially destructive command. Stop and explain the "
    "operation to the user. Do not bypass the hook or repeat the same operation "
    "through another tool. The user can review and perform it manually."
)
STASH_REASON = (
    "Guard blocked a working-tree stash. Stashing can temporarily remove other "
    "sessions' uncommitted changes from a shared checkout. Preserve your work "
    "with an explicit-path commit or a separate checkout."
)
PROCESS_REASON = (
    "Guard blocked a machine-wide agent process termination. It can stop other "
    "sessions. Use the lifecycle control for a process you started, or its "
    "verified PID, after confirming ownership."
)

# First match wins. These are conservative text patterns, not a shell parser.
BLOCK_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bmigrate\s+reset\b", re.I), DENY_REASON),
    # Exclude Git's rm subcommand and Docker's --rm option, not their whole line.
    (re.compile(
        r"(?<!git\s)(?<!-)\brm\s+"
        r"(?=(?:-\S+\s+)*(?:-(?!-)[A-Za-z]*r[A-Za-z]*|--recursive)(?:\s|$))"
        r"(?=(?:-\S+\s+)*(?:-(?!-)[A-Za-z]*f[A-Za-z]*|--force)(?:\s|$))"
        r"(?:-\S+\s+)+(?:--\s+)?[\"']?"
        r"(?:/|\.(?![A-Za-z0-9_])|\*|~|\$HOME\b|\.(?:git|env)(?![A-Za-z0-9_]))",
        re.I,
    ), DENY_REASON),
    (re.compile(r"\b(?:rmdir|rd)\s+/(?:s|q)[^\n;&|]*(/|\.\s*$|\*\s*$)", re.I), DENY_REASON),
    (re.compile(r"\bremove-item\b[^\n;&|]*-recurse\b[^\n;&|]*\s(?:\.(?:\s|$)|\*(?:\s|$)|[a-z]:[\\/])", re.I), DENY_REASON),
    (re.compile(r"\bgit\s+push\b[^\n;&|]*(--force|-f\b)", re.I), DENY_REASON),
    (re.compile(r"\bgit\s+reset\s+--hard\b", re.I), DENY_REASON),
    (re.compile(r"\bgit\s+(?:checkout|restore)\s+(?:--\s+)?\.(?![A-Za-z0-9_])", re.I), DENY_REASON),
    (re.compile(r"\bgit\s+restore\s+--staged\s+(?:--\s+)?\.(?![A-Za-z0-9_])", re.I), DENY_REASON),
    (re.compile(r"\bgit\s+clean\s+-[a-z]*f[a-z]*\b", re.I), DENY_REASON),
    (re.compile(r"\bgit\s+branch\s+(?-i:-D)\b", re.I), DENY_REASON),
    (re.compile(r"\bgit\s+stash\s+(?:drop|clear)\b", re.I), DENY_REASON),
    (re.compile(r"\bgit\s+stash\b(?!\s+(?:list|show|pop|apply|branch|drop|clear)\b)", re.I), STASH_REASON),
    (re.compile(r"\bDROP\s+(?:TABLE|DATABASE)\b", re.I), DENY_REASON),
    (re.compile(r"\bdocker\s+system\s+prune\b", re.I), DENY_REASON),
    (re.compile(r"\bdocker\s+volume\s+rm\b", re.I), DENY_REASON),
    (re.compile(r"\bdocker(?:\s+|-)?compose\s+down\b[^\n;&|]*\s(?:-v\b|--volumes\b)", re.I), DENY_REASON),
    (re.compile(r"\bchmod\s+(?:-R\s+)?777\b", re.I), DENY_REASON),
    (re.compile(r"\bshred\b|\bmkfs\.|\bformat\s+[a-z]:", re.I), DENY_REASON),
    (re.compile(r"\btaskkill\b[^\n;&|]*\bim\b[^\n;&|]*\b(?:codex|claude)\b", re.I), PROCESS_REASON),
    (re.compile(r"\b(?:pkill|killall)\s+(?:-\S+\s+)*(?:codex|claude)\b", re.I), PROCESS_REASON),
    (re.compile(r"\bstop-process\b[^\n;&|]*\b(?:codex|claude)\b", re.I), PROCESS_REASON),
    (re.compile(r"\b(?:codex|claude)\b[^\n]*\|\s*[^\n]*\bstop-process\b", re.I), PROCESS_REASON),
]

SAFE_SEARCH_COMMANDS = {"rg", "ripgrep", "grep", "select-string", "findstr"}
COMMAND_WRAPPERS = {"&", "command", "sudo"}


def command_from_payload(payload: dict[str, Any]) -> str:
    tool_name = str(payload.get("tool_name") or "").lower()
    if tool_name not in {"bash", "powershell", "shell_command", "functions.shell_command"}:
        return ""
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        raise ValueError("Shell tool_input must be an object.")
    command = tool_input.get("command")
    if not isinstance(command, str):
        raise ValueError("Shell tool_input.command must be a string.")
    return command


def split_shell_segments(command: str) -> list[str]:
    """Split separators outside quotes; intentionally not a full shell parser."""
    segments: list[str] = []
    start = 0
    in_single = in_double = escape = False
    i = 0
    while i < len(command):
        ch = command[i]
        if escape:
            escape = False
            i += 1
            continue
        if in_double and ch in {"\\", "`"}:
            escape = True
            i += 1
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            if ch in {";", "\n"}:
                segments.append(command[start:i + 1])
                start = i + 1
            elif ch in {"&", "|"}:
                if i + 1 < len(command) and command[i + 1] == ch:
                    segments.append(command[start:i + 2])
                    start = i + 2
                    i += 1
                else:
                    segments.append(command[start:i + 1])
                    start = i + 1
        i += 1
    segments.append(command[start:])
    return segments


def command_words(segment: str, limit: int = 4) -> list[str]:
    words: list[str] = []
    i = 0
    while i < len(segment) and len(words) < limit:
        while i < len(segment) and segment[i].isspace():
            i += 1
        if i >= len(segment):
            break
        quote = segment[i] if segment[i] in {"'", '"'} else ""
        if quote:
            i += 1
            start = i
            while i < len(segment) and segment[i] != quote:
                i += 1
            words.append(segment[start:i])
            i += 1
        else:
            start = i
            while i < len(segment) and not segment[i].isspace():
                i += 1
            words.append(segment[start:i])
    return words


def command_basename(word: str) -> str:
    base = word.strip().strip("'\"").replace("\\", "/").rsplit("/", 1)[-1].lower()
    return base[:-4] if base.endswith(".exe") else base


def is_readonly_search_segment(segment: str) -> bool:
    words = command_words(segment)
    idx = 0
    while idx < len(words):
        base = command_basename(words[idx])
        if base in COMMAND_WRAPPERS or re.fullmatch(r"[A-Za-z_]\w*=.*", words[idx]):
            idx += 1
            continue
        if base == "git" and idx + 1 < len(words):
            if command_basename(words[idx + 1]) != "grep":
                return False
            return not git_grep_pager_arguments(segment)
        if base in {"rg", "ripgrep"} and re.search(r"(?:^|\s)--pre(?:[=\s]|$)", segment):
            return False
        return base in SAFE_SEARCH_COMMANDS
    return False


def git_grep_pager_arguments(segment: str) -> list[str]:
    """Read explicit pager options, preserving option-like search data."""
    words = command_words(segment, limit=len(segment))
    idx = 0
    while idx < len(words) and (
        command_basename(words[idx]) in COMMAND_WRAPPERS
        or re.fullmatch(r"[A-Za-z_]\w*=.*", words[idx])
    ):
        idx += 1
    if idx + 1 >= len(words) or command_basename(words[idx]) != "git" or command_basename(words[idx + 1]) != "grep":
        return []
    pagers: list[str] = []
    idx += 2
    while idx < len(words):
        argument = words[idx]
        if argument == "--":
            break
        if argument in {"-e", "--regexp", "-f", "--file"}:
            idx += 2
            continue
        if argument.startswith("-O"):
            pagers.append(argument[2:])
        elif argument == "--open-files-in-pager":
            pagers.append("")
        elif argument.startswith("--open-files-in-pager="):
            pagers.append(argument.split("=", 1)[1])
        idx += 1
    return pagers


def strip_safe_quoted_literals(segment: str) -> str:
    """Remove inert quoted search data while retaining expansion markers."""
    out: list[str] = []
    i = 0
    while i < len(segment):
        ch = segment[i]
        if ch == "'":
            end = segment.find("'", i + 1)
            if end == -1:
                out.append(segment[i:])
                break
            out.append("''")
            i = end + 1
            continue
        if ch == '"':
            j = i + 1
            escaped = False
            body_chars: list[str] = []
            while j < len(segment):
                cur = segment[j]
                if escaped:
                    body_chars.append(cur)
                    escaped = False
                elif cur in {"\\", "`"}:
                    escaped = True
                    body_chars.append(cur)
                elif cur == '"':
                    break
                else:
                    body_chars.append(cur)
                j += 1
            if j >= len(segment):
                out.append(segment[i:])
                break
            body = "".join(body_chars)
            out.append(segment[i:j + 1] if any(x in body for x in ("$", "`", "<")) else '""')
            i = j + 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def strip_readonly_search_patterns(command: str) -> str:
    sanitized: list[str] = []
    for segment in split_shell_segments(command):
        if is_readonly_search_segment(segment):
            sanitized.append(strip_safe_quoted_literals(segment))
        else:
            sanitized.append(segment)
            # Scan pager bodies separately so a quoted '-Ogit ...' still
            # exposes the executable command to the existing rule patterns.
            sanitized.extend(git_grep_pager_arguments(segment))
    return "\n".join(sanitized)


def strip_commit_message(command: str) -> str:
    """Remove literal commit messages; retain potentially executable content."""
    if not re.search(r"\bgit\s+commit\b", command, re.I):
        return command
    stripped = command
    for marker in (r"'([A-Za-z_]\w*)'", r'"([A-Za-z_]\w*)"'):
        stripped = re.sub(
            r'-m\s+"\$\(\s*cat\s+<<-?\s*' + marker
            + r'(?>[\s\S]*?^\s*\1\s*$)\s*\)"',
            " ", stripped, flags=re.MULTILINE,
        )
    for flag in (r"-m\s+", r"--message=?\s*"):
        stripped = re.sub(flag + r"'[^']*'", " ", stripped)
        stripped = re.sub(flag + r'"[^"`$<]*"', " ", stripped)
    return stripped


def deny_payload(event_name: str, reason: str) -> dict[str, Any]:
    if event_name == "PermissionRequest":
        return {"hookSpecificOutput": {
            "hookEventName": event_name,
            "decision": {"behavior": "deny", "message": reason},
        }}
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}


def check_command(command: str) -> str | None:
    scan_target = strip_readonly_search_patterns(strip_commit_message(command))
    for pattern, reason in BLOCK_PATTERNS:
        if pattern.search(scan_target):
            return reason
    return None


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict):
            raise ValueError("Hook input must be an object.")
        event = payload.get("hook_event_name", "PreToolUse")
        if not isinstance(event, str):
            raise ValueError("hook_event_name must be a string.")
        if event not in {"PreToolUse", "PermissionRequest"}:
            return 0
        command = command_from_payload(payload)
    except (ValueError, OSError) as exc:
        print(f"[guard] Invalid hook input: {exc}", file=sys.stderr)
        return 2
    reason = check_command(command)
    if reason:
        print(json.dumps(deny_payload(event, reason)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
