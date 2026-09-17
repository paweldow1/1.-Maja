#!/usr/bin/env bash
# Start Kwerenda on macOS/Linux:       ./start.sh
# Any other command works the same way, from any folder:
#   ./start.sh doctor
#   ./start.sh update
#   ./start.sh gui
# (no "python -m kwerenda ..." needed — this script finds the right Python for
# you, wherever it is called from)
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "First run — preparing a private environment…"
  python3 -m venv .venv
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet -r requirements.txt
fi
if [ "$#" -eq 0 ]; then
  set -- gui
fi
exec ./.venv/bin/python -m kwerenda "$@"
