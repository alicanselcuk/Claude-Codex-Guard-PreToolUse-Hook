# Agent installation instructions

This repository contains a general shell-command hook for Claude Code and Codex.

When asked to install it into another project:

1. Confirm the target from the user's current project context. Clone this repository outside that target; do not copy another project's history or configuration.
2. Read `README.md`, `guard.py`, and `install.py`. Check that Python 3.11+ and lifecycle hooks are available. Use the selected agent's current official hook documentation if its schema differs.
3. Run `python -m unittest discover -s tests -v` here. These tests pass command strings as data and never execute destructive examples.
4. Run `python install.py --target <project> --agent claude|codex|both --dry-run`, then install the requested integration. Choose the agent the user is using; use `both` only when both are requested.
5. Read back the resulting settings. Preserve unrelated hooks, permissions, environment settings, and local changes. Do not weaken the existing policy or bypass hook trust.
6. Report installed files and the required restart/trust steps. Test safe and denied JSON payloads directly, and distinguish this from observing the real agent invoke the hook. Do not run destructive commands to prove blocking.

Installed configuration contains local absolute paths. Keep configuration backups private and re-run installation after moving a project. Do not add personal paths, domains, secrets, private infrastructure details, or project-specific policies to this public repository.

For changes here, keep Claude and Codex decisions aligned through the shared `guard.py`, preserve existing settings in the installer, and run the tests. Do not expand this text-pattern guard into a shell parser or claim complete security coverage.
