#!/usr/bin/env bash
# Uruchomienie Kwerendy na macOS/Linuksie: ./start.sh
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "Pierwsze uruchomienie – przygotowuję środowisko…"
  python3 -m venv .venv
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet -r requirements.txt
fi
exec ./.venv/bin/python -m kwerenda gui "$@"
