@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=%~dp0..\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo Non trovo l'ambiente virtuale. Avvia prima avvia_idoma_2.bat.
  pause
  exit /b 1
)
"%PYTHON%" -m idoma_v2.desktop_agent
pause
