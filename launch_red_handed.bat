@echo off
setlocal
cd /d "%~dp0" || exit /b 1

if not exist ".venv\Scripts\python.exe" (
    echo Red-Handed virtual environment was not found.
    echo. 
    echo Expected:
    echo .venv\Scripts\python.exe
    echo.
    echo Follow the installation steps in README.md first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" "run_red_handed.py"
set "red_handed_exit_code=%errorlevel%"
if not "%red_handed_exit_code%"=="0" (
    echo.
    echo Red-Handed exited with an error. See the message above.
    pause
)
exit /b %red_handed_exit_code%