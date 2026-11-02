@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=%~dp0..\.venv\Scripts\python.exe"
set "PYTHONW=%~dp0..\.venv\Scripts\pythonw.exe"
if not exist "%PYTHON%" (
  echo Non trovo l'ambiente virtuale PersonalAI\.venv.
  echo Verifica che IDOMA sia nella cartella PersonalAI\IDOMA_2.0.
  pause
  exit /b 1
)
if not exist "%PYTHONW%" set "PYTHONW=%PYTHON%"
"%PYTHON%" -c "import PySide6, fastapi, uvicorn, pypdf, docx, openpyxl, pptx, dotenv, sounddevice, vosk, faster_whisper, pyttsx3, numpy" >nul 2>&1
if errorlevel 1 (
  echo Installazione delle dipendenze di IDOMA...
  "%PYTHON%" -m pip install -r requirements-v2.txt
  if errorlevel 1 (
    echo Installazione non riuscita.
    pause
    exit /b 1
  )
)
start "" "%PYTHONW%" "%~dp0avvia_desktop.py"
exit /b 0
