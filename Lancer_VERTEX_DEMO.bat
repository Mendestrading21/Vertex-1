@echo off
REM VERTEX TEST 1.0 - mode DEMO, donnees fictives explicitement marquees.
cd /d "%~dp0"
title VERTEX TEST 1.0 - DEMO
cls

where python >nul 2>nul
if errorlevel 1 (
  echo [X] Python manquant: https://www.python.org/downloads/
  pause
  exit /b 1
)

if not exist ".venv" (
  python -m venv .venv
  call ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
  call ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
)

set DEMO=1
set NO_IBKR=1
set START_ON_IMPORT=0
REM  IPv4 explicite (voir Lancer_VERTEX.bat) : `localhost` peut resoudre en ::1.
start "" cmd /c "timeout /t 5 >nul & start http://127.0.0.1:5002"
".venv\Scripts\python.exe" -m vertex
pause
