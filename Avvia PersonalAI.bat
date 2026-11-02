
@echo off
cd /d "%~dp0"

echo.
echo ==================================
echo       PERSONAL AI
echo ==================================
echo.
echo Avvio in corso...

".venv\Scripts\python.exe" main.py

if errorlevel 1 (
    echo.
    echo PersonalAI si e' chiuso con un errore.
    pause
)
