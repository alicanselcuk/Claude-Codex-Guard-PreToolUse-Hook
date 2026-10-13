# Claude & Codex Guard — PreToolUse Hook

A small, local guard that checks shell commands before Claude Code or Codex runs them. It catches common destructive operations and returns an explicit hook denial. One Python policy serves both agents; `guard.sh` is the Bash entry point.

No API keys, external services, telemetry, or third-party Python packages.

## Install with your coding agent

Give Claude Code or Codex this prompt:

> Install the guard from https://github.com/alicanselcuk/Claude-Codex-Guard-PreToolUse-Hook in this project. Clone it outside this project, read README.md and AGENTS.md, run its tests, and use install.py for the agent I am using. Preserve existing settings and hooks. Show the resulting configuration and explain how to activate and verify it.

## Manual installation

Requirements: Git, Python **3.11+**, and an agent version supporting the documented lifecycle hooks. Bash is needed only for `guard.sh`; the installer invokes Python directly, including on Windows.

```sh
git clone https://github.com/alicanselcuk/Claude-Codex-Guard-PreToolUse-Hook.git
cd Claude-Codex-Guard-PreToolUse-Hook
python3 -m unittest discover -s tests -v
python3 install.py --target /path/to/your/project --agent both --dry-run
python3 install.py --target /path/to/your/project --agent both
```

On Windows, use `python` or `py -3` instead of `python3`, and quote paths containing spaces. Select `--agent claude` or `--agent codex` to install only one integration.

The installer copies `guard.py`, `guard.sh`, and `LICENSE` into `.agent-guard/`, then merges hooks into `.claude/settings.json` and/or `.codex/hooks.json`. Existing settings and unrelated hooks remain. Changed settings get a sibling `.guard-backup-<number>` file. Keep backups private: they may contain your existing configuration. Repeating installation updates the installed guard without adding duplicate handlers. It replaces local edits to the installed scripts.

Generated commands use your Python interpreter and absolute project path, so they also work when the agent starts from a subdirectory. Re-run installation after moving the project or changing Python. Generated paths are machine-specific; review them before sharing project configuration.

Restart your agent, then inspect `/hooks`. **Codex requires reviewing and trusting the hook definition and the project configuration layer.** If hooks are disabled in your agent settings, enable them before relying on the guard. Installing files alone does not establish activation. See [OpenAI Docs: hooks](https://learn.chatgpt.com/docs/hooks) and [Claude Code hooks](https://code.claude.com/docs/en/hooks).

## What it blocks

| Category | Examples |
| --- | --- |
| Git history and local work | Force push (including `--force-with-lease`), hard reset, forced clean, forced branch deletion, tree-wide checkout/restore, stash creation/drop/clear |
| Files and disks | Common `rm -rf` forms targeting absolute paths, `./` paths, home directories, globs, `.git`, or `.env`; selected Windows recursive deletions; `shred`, `mkfs.*`, drive formatting |
| Database destruction | `migrate reset`, `DROP TABLE`, `DROP DATABASE` |
| Docker data | System prune, volume removal, Compose down with volume removal |
| Permissions | `chmod 777`, `chmod -R 777` |
| Other agent sessions | Name/image-based termination of `claude` or `codex` processes |

Ordinary Git reads, normal pushes, `git clean -n`, targeted file restores, branch changes, stash reads/restores, `chmod 755`, Docker `--rm`, and build-cache cleanup such as `rm -rf .next` pass the guard. Passing the guard leaves normal agent permissions in place. Migration strategy and recursive-search preferences belong to your project's instructions; `prisma db push` and `grep -r` are not prohibited here.

Literal commit messages and quoted read-only search patterns are excluded from scanning when they contain no shell expansion. Command substitutions, executable wrappers, destructive suffixes, and search commands with pager/preprocessor options are still scanned.

## Verify without executing a dangerous command

Pipe a hook payload into the guard. **The command below is JSON data; the guard never executes it.**

```sh
printf '%s' '{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"git reset --hard"}}' | python3 guard.py
```

Expect `hookSpecificOutput.permissionDecision` to be `deny`. Changing the command to `git status` should produce no output. `PermissionRequest` uses `hookSpecificOutput.decision.behavior` instead. Tests cover both events, Windows hook commands, installation, preservation of existing settings, and repeat installation.

The hook matches Claude's `Bash` and `PowerShell` tools and Codex's canonical `Bash` shell hook, including unified exec. It ignores file edits and other non-shell tools. Review activation in your real agent separately from these script tests.

## Limits and failure behavior

This is a conservative **regex guard**, not a security sandbox or complete shell parser. Encoded/obfuscated commands, aliases, unrecognized option arrangements, variable-built commands and paths, or indirect script execution can escape detection. Quoting and heredocs can also cause false positives. Never use it as the sole protection for secrets, production data, or untrusted code.

The script rejects malformed hook input and unsupported Python with exit code 2; `guard.sh` also returns 2 when no compatible interpreter is found. A valid unmatched shell command returns 0 with no output. Agent-side hook startup failures, timeouts, disabled hooks, and missing trust can leave the guard inactive; inspect your agent's hook diagnostics.

To customize the policy, edit `BLOCK_PATTERNS` in the source `guard.py`, add a meaningful regression case, run the tests, and reinstall. Both agents then receive the same policy. On denial, stop and explain the blocked operation; do not try to evade the guard.

## Remove

Remove only the handlers referring to `.agent-guard/guard.py` from `PreToolUse` and `PermissionRequest` in the selected agent's configuration. Keep all unrelated handlers and settings. Restart and inspect `/hooks`. Once neither agent references it, you can manually remove `.agent-guard/`. Review backups instead of restoring an old configuration over newer settings.

## Development

```sh
python3 -m unittest discover -s tests -v
bash -n guard.sh
```

MIT licensed. This project is independent of Anthropic and OpenAI.
