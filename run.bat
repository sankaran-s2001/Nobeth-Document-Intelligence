@echo off
setlocal enabledelayedexpansion

REM =========================================================================
REM Nobeth Document Intelligence - Windows One-Click Launcher
REM Production-Ready, Beginner-Proof Startup Script
REM Nobeth Analytics
REM =========================================================================

title Nobeth Document Intelligence - Launcher

REM 1. Ensure working directory is strictly project root
set "PROJECT_ROOT=%~dp0"
cd /d "!PROJECT_ROOT!"

echo =========================================================================
echo             Nobeth Document Intelligence - Windows Launcher
echo                 Official Nobeth Analytics Product
echo =========================================================================
echo.

REM -------------------------------------------------------------------------
REM 2. Multi-Layer Python Detection
REM    Layer A: Check 'python' in PATH and verify it is executable
REM    Layer B: Check Windows Python Launcher 'py -3'
REM    Layer C: Check standard default install paths [if PATH was not set]
REM -------------------------------------------------------------------------
set "PYTHON_CMD="

REM Test standard 'python'
where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=python"
)

REM Test Windows Python Launcher 'py'
if "!PYTHON_CMD!"=="" (
    where py >nul 2>&1
    if not errorlevel 1 (
        py -3 -c "import sys" >nul 2>&1
        if not errorlevel 1 set "PYTHON_CMD=py -3"
    )
)

REM Check common standard install paths in case Python was installed without 'Add to PATH'
if "!PYTHON_CMD!"=="" (
    for %%P in (
        "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
        "C:\Program Files\Python312\python.exe"
        "C:\Program Files\Python311\python.exe"
        "C:\Program Files\Python310\python.exe"
        "C:\Python312\python.exe"
        "C:\Python311\python.exe"
        "C:\Python310\python.exe"
    ) do (
        if "!PYTHON_CMD!"=="" (
            if exist %%P (
                %%P -c "import sys" >nul 2>&1
                if not errorlevel 1 set "PYTHON_CMD=%%~P"
            )
        )
    )
)

REM If Python is still not found, provide crystal-clear guidance
if "!PYTHON_CMD!"=="" (
    echo [ERROR] Python is not installed or could not be found on this computer.
    echo.
    echo Nobeth Document Intelligence requires Python 3.10, 3.11, or 3.12.
    echo.
    echo Quick Installation Options:
    echo.
    echo   Option 1 - Automated via Windows Package Manager [Recommended]:
    echo     Open Command Prompt or PowerShell and run:
    echo       winget install Python.Python.3.11
    echo.
    echo   Option 2 - Manual Download:
    echo     1. Visit: https://www.python.org/downloads/
    echo     2. Download Python 3.11, 3.10, or 3.12 installer.
    echo     3. IMPORTANT: Check "Add Python to PATH" during installation.
    echo     4. Re-run this run.bat file after installation completes.
    echo.
    pause
    exit /b 1
)

REM -------------------------------------------------------------------------
REM 3. Verify Python Version (Must be >= 3.10 and < 3.13)
REM -------------------------------------------------------------------------
!PYTHON_CMD! -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) and sys.version_info < (3, 13) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Incompatible Python version detected.
    for /f "tokens=*" %%v in ('!PYTHON_CMD! --version 2^>^&1') do echo   Current Version: %%v
    echo.
    echo Nobeth Document Intelligence requires Python 3.10, 3.11, or 3.12.
    echo Please install a compatible Python version from https://www.python.org/downloads/
    echo Remember to check "Add Python to PATH" during setup.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('!PYTHON_CMD! --version 2^>^&1') do echo [*] System Python: %%v

REM -------------------------------------------------------------------------
REM 4. Self-Healing Virtual Environment (.venv)
REM    Handles fresh setup and auto-repairs stale/copied virtual environments
REM -------------------------------------------------------------------------
set "RECREATE_VENV=0"
if exist ".venv\Scripts\python.exe" (
    REM Test if the existing venv is actually functional
    ".venv\Scripts\python.exe" -c "import sys" >nul 2>&1
    if errorlevel 1 (
        echo [WARNING] Existing virtual environment in .venv is broken or was copied from another PC.
        echo [*] Re-creating virtual environment for this computer...
        set "RECREATE_VENV=1"
    )
) else (
    set "RECREATE_VENV=1"
)

if "!RECREATE_VENV!"=="1" (
    if exist ".venv" (
        echo [*] Cleaning stale virtual environment...
        rmdir /s /q .venv >nul 2>&1
    )
    echo [*] Setting up isolated Python virtual environment in .venv...
    !PYTHON_CMD! -m venv .venv
    if errorlevel 1 (
        echo.
        echo [ERROR] Failed to create virtual environment.
        echo Please ensure you have write permissions in this folder:
        echo   !PROJECT_ROOT!
        echo.
        pause
        exit /b 1
    )
    echo [*] Virtual environment created successfully.
    set "NEW_VENV=1"
) else (
    echo [*] Virtual environment verified [.venv].
    set "NEW_VENV=0"
)

REM -------------------------------------------------------------------------
REM 5. Smart Dependency Verification (Fast Launch: Skips if Already Satisfied)
REM -------------------------------------------------------------------------
if not exist "requirements.txt" (
    echo [ERROR] 'requirements.txt' was not found in the project directory.
    echo Please make sure all project files are extracted properly.
    echo.
    pause
    exit /b 1
)

set "NEED_DEPS=0"
if "!NEW_VENV!"=="1" set "NEED_DEPS=1"
if not exist ".venv\.installed_requirements" set "NEED_DEPS=1"

REM Verify core packages import cleanly
if "!NEED_DEPS!"=="0" (
    ".venv\Scripts\python.exe" -c "import fastapi, uvicorn, google.genai, dotenv, pydantic, pymupdf, docx, fpdf, uharfbuzz" >nul 2>&1
    if errorlevel 1 set "NEED_DEPS=1"
)

REM If requirements.txt has changed compared to our marker, trigger re-installation
if "!NEED_DEPS!"=="0" (
    fc /b requirements.txt ".venv\.installed_requirements" >nul 2>&1
    if errorlevel 1 set "NEED_DEPS=1"
)

if "!NEED_DEPS!"=="1" (
    echo [*] Installing required Python dependencies from requirements.txt...
    echo     [This only runs on initial setup or when requirements change]
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [ERROR] Failed to install required Python packages from requirements.txt.
        echo Please check your internet connection, or try running manually:
        echo   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
    copy /y requirements.txt ".venv\.installed_requirements" >nul 2>&1
    echo [*] Dependencies installed and verified.
) else (
    echo [*] Dependencies verified. Ready to launch.
)

REM -------------------------------------------------------------------------
REM 6. Manage Configuration File (.env) and Validate API Key
REM -------------------------------------------------------------------------
if not exist ".env" (
    if exist ".env.example" (
        echo [*] Initializing .env configuration from .env.example...
        copy ".env.example" ".env" >nul
    ) else (
        echo [*] Generating default .env configuration...
        (
            echo # Google Gemini API configuration
            echo GEMINI_API_KEY=
            echo GEMINI_PRIMARY_MODEL=gemini-3.5-flash-lite
            echo GEMINI_FALLBACK_MODEL=gemini-3.1-flash-lite
            echo HOST=127.0.0.1
            echo PORT=8000
            echo MAX_UPLOAD_MB=25
            echo MAX_PDF_PAGES=50
            echo MAX_CONCURRENT_JOBS=2
            echo JOB_RETENTION_HOURS=24
            echo OPEN_BROWSER=true
        ) > ".env"
    )
    echo [*] Created .env file.
)

REM Check if GEMINI_API_KEY is configured in .env or .env.example
".venv\Scripts\python.exe" -c "import os, sys, shutil; from dotenv import load_dotenv; load_dotenv('.env'); k = os.getenv('GEMINI_API_KEY', '').strip(); (sys.exit(0) if (k and not k.startswith('your_') and not k.startswith('YOUR_') and len(k) >= 20) else None); load_dotenv('.env.example', override=True); ke = os.getenv('GEMINI_API_KEY', '').strip(); (shutil.copyfile('.env.example', '.env') or sys.exit(0)) if (ke and not ke.startswith('your_') and not ke.startswith('YOUR_') and len(ke) >= 20) else sys.exit(1)" >nul 2>&1
if errorlevel 1 (
    echo.
    echo -------------------------------------------------------------------------
    echo [NOTE] Google Gemini API Key is not yet configured in your .env file.
    echo        - Get your free Gemini API key: https://aistudio.google.com/
    echo        - Open '.env' in Notepad and set:
    echo            GEMINI_API_KEY=your_actual_api_key_here
    echo.
    echo Opening .env in Notepad for you...
    start notepad.exe .env
    echo -------------------------------------------------------------------------
    echo.
    echo Press any key after saving your API key in Notepad to continue...
    pause >nul
)

REM -------------------------------------------------------------------------
REM 7. Port Conflict Check (Port 8000)
REM -------------------------------------------------------------------------
netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo [WARNING] Port 8000 appears to be occupied by another process.
    echo           If Nobeth Document Intelligence is already running, open:
    echo             http://127.0.0.1:8000
    echo           Otherwise, close the conflicting program before launching.
    echo.
)

REM -------------------------------------------------------------------------
REM 8. Launch Application & Auto-Open Browser
REM -------------------------------------------------------------------------
echo [*] Launching Nobeth Document Intelligence...
echo [*] Server URL: http://127.0.0.1:8000
echo [*] Press Ctrl+C in this terminal window at any time to cleanly stop the server.
echo.

start "" powershell -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8000'"

".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo.
echo =========================================================================
echo Nobeth Document Intelligence has closed.
echo =========================================================================
pause
