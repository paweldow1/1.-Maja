#!/usr/bin/env bash
# Start Kwerenda on macOS/Linux:  ./start.sh
# For an icon on the desktop instead:  python3 install_desktop_icon.py
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "First run — preparing a private environment…"
  python3 -m venv .venv
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet -r requirements.txt
fi
exec ./.venv/bin/python -m kwerenda gui "$@"
