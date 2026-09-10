@echo off
REM Start Kwerenda on Windows: double-click this file.
REM For an icon on the desktop instead: python install_desktop_icon.py
cd /d "%~dp0"
if not exist .venv (
  echo First run - preparing a private environment...
  python -m venv .venv
  .venv\Scripts\python -m pip install --quiet --upgrade pip
  .venv\Scripts\python -m pip install --quiet -r requirements.txt
)
.venv\Scripts\python -m kwerenda gui %*
pause
