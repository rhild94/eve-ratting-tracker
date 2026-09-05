@echo off
setlocal
cd /d "%~dp0"
title EVE Ratting Tracker

set "PY=py"
%PY% --version >nul 2>&1
if errorlevel 1 set "PY=python"
%PY% --version >nul 2>&1
if errorlevel 1 (
  echo Python 3 is required. Install Python from python.org and enable "Add Python to PATH".
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating local Python environment...
  %PY% -m venv .venv
  if errorlevel 1 goto :fail
)

echo Checking application dependencies...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :fail

".venv\Scripts\python.exe" launcher.py
exit /b 0

:fail
echo.
echo Setup failed. The files were not deleted or changed.
pause
exit /b 1
