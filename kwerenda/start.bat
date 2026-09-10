@echo off
REM Uruchomienie Kwerendy w Windowsie: kliknij dwukrotnie ten plik.
cd /d "%~dp0"
if not exist .venv (
  echo Pierwsze uruchomienie - przygotowuje srodowisko...
  python -m venv .venv
  .venv\Scripts\python -m pip install --quiet --upgrade pip
  .venv\Scripts\python -m pip install --quiet -r requirements.txt
)
.venv\Scripts\python -m kwerenda gui %*
pause
