@echo off
cd /d "%~dp0"

echo ========================================
echo   Augmented LLM - Chat + MCP + RAG
echo ========================================

:: venv
if not exist ".venv\Scripts\python.exe" (
    echo Creating venv...
    python -m venv .venv
)

:: dependencies
echo Checking dependencies...
.venv\Scripts\python.exe -c "import yaml" 2>nul
if errorlevel 1 (
    echo Installing dependencies...
    .venv\Scripts\python.exe -m pip install -r requirements.txt -q
)
echo.

echo Starting Agent...
echo.

.venv\Scripts\python.exe main.py
pause
