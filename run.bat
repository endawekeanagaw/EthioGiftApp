@echo off
setlocal
cd /d "%~dp0"
title GiftBridge Ethiopia v0.3 - Local Sandbox

echo ============================================================
echo      GiftBridge Ethiopia v0.3 - Local Demo

echo      NO REAL PAYMENTS OR GIFT VALUE

echo ============================================================
echo.
if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating a local Python virtual environment...
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 -m venv .venv
  ) else (
    python -m venv .venv
  )
  if errorlevel 1 goto :error
)

".venv\Scripts\python.exe" -c "import uvicorn,fastapi,sqlalchemy" >nul 2>nul
if errorlevel 1 (
  echo [2/3] Installing required Python packages for first-time setup...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :error
)

echo [3/3] Preparing demo sample accounts and merchants...
".venv\Scripts\python.exe" -m backend.seed
if errorlevel 1 goto :error

echo.
".venv\Scripts\python.exe" launcher.py
if errorlevel 1 goto :error
exit /b 0

:error
echo.
echo Startup failed. Read the error message above, then press any key.
pause >nul
exit /b 1
