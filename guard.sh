#!/usr/bin/env bash
# Portable entry point. The shared policy is in guard.py (Python 3.11+).
DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)" || exit 2
PYCHECK='import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'

if command -v python >/dev/null 2>&1 && python -c "$PYCHECK" >/dev/null 2>&1; then
  exec python "$DIR/guard.py"
fi
if command -v py >/dev/null 2>&1 && py -3 -c "$PYCHECK" >/dev/null 2>&1; then
  exec py -3 "$DIR/guard.py"
fi
if command -v python3 >/dev/null 2>&1 && python3 -c "$PYCHECK" >/dev/null 2>&1; then
  exec python3 "$DIR/guard.py"
fi
echo "[guard] Python 3.11+ is required; refusing to run without the guard." >&2
exit 2
