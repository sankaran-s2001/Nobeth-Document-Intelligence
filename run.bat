@echo off
setlocal enabledelayedexpansion

title Nobeth Document Intelligence

echo [START] Nobeth Document Intelligence
echo [INFO] Official Nobeth Analytics Product
echo.

:: 1. Resolve Project Root
cd /d "%~dp0"
set "PROJECT_DIR=%~dp0"

:: 2. Check Python Availability
echo [CHECK] Python environment
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python was not found in your PATH.
    echo [INFO] Please install Python 3.11 or 3.12 and ensure it is added to your PATH.
    pause
    exit /b 1
)

:: 3. Setup or Reuse Virtual Environment
if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Creating Python virtual environment in .venv ...
    python -m venv .venv
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created
) else (
    echo [OK] Virtual environment ready
)

:: 4. Check Dependencies
echo [CHECK] Dependencies
".venv\Scripts\python.exe" -c "import fastapi, uvicorn, pydantic, pymupdf, docx, fpdf" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [INFO] Installing required dependencies from requirements.txt ...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Dependency installation failed.
        pause
        exit /b 1
    )
    echo [OK] Dependencies installed
) else (
    echo [OK] Dependencies ready
)

:: 5. Check Environment File (.env)
echo [CHECK] Gemini configuration
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [WARN] Created .env from .env.example.
        echo [WARN] Please edit .env and set your GEMINI_API_KEY for live AI extraction.
    ) else (
        echo [WARN] .env file not found.
    )
) else (
    ".venv\Scripts\python.exe" -c "import os; from dotenv import load_dotenv; load_dotenv(); key = os.getenv('GEMINI_API_KEY', '').strip(); exit(0 if key else 1)" >nul 2>&1
    if %ERRORLEVEL% equ 0 (
        echo [OK] Gemini API key configured
    ) else (
        echo [WARN] GEMINI_API_KEY is empty in .env. Live AI extraction requires a valid key.
    )
)

:: 6. Check Port 8000
netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [WARN] Port 8000 appears to be occupied.
    echo [INFO] If Nobeth Document Intelligence is already running, open http://127.0.0.1:8000
    echo [INFO] To stop conflicting processes, close that application or update PORT in .env.
)

:: 7. Launch Browser in background after a brief delay
start "" powershell -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8000'"

:: 8. Start Uvicorn in the foreground
echo [SERVER] Starting FastAPI server on http://127.0.0.1:8000
echo [INFO] Press Ctrl+C in this window to stop the server at any time.
echo.

".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

pause

