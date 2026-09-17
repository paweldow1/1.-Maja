@echo off
REM Start Kwerenda on Windows: double-click this file, or from a terminal:
REM   start.bat doctor
REM   start.bat update
REM   start.bat gui
REM (no "python -m kwerenda ..." needed - this finds the right Python for you)
cd /d "%~dp0"
if not exist .venv (
  echo First run - preparing a private environment...
  python -m venv .venv
  .venv\Scripts\python -m pip install --quiet --upgrade pip
  .venv\Scripts\python -m pip install --quiet -r requirements.txt
)
.venv\Scripts\python -m kwerenda %*
pause
