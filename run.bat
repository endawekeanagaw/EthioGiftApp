@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo GiftBridge virtual environment missing.
  echo Run: python -m venv .venv
  echo Then: .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)
echo Starting GiftBridge Ethiopia sandbox...
echo Open http://127.0.0.1:8000
".venv\Scripts\python.exe" -m uvicorn backend.main:app --reload
pause
