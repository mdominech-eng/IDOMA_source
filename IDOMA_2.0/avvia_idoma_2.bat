@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=%~dp0..\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo Non trovo l'ambiente virtuale del progetto: ..\.venv
  echo Creo un ambiente virtuale dedicato a IDOMA 2.0...
  py -3 -m venv "%~dp0.venv"
  set "PYTHON=%~dp0.venv\Scripts\python.exe"
)
if not exist "%PYTHON%" (
  echo ERRORE: Python non trovato. Installa Python 3.11 o superiore.
  pause
  exit /b 1
)
"%PYTHON%" -m pip install -r requirements-v2.txt
if errorlevel 1 (
  echo Errore durante l'installazione delle dipendenze.
  pause
  exit /b 1
)
echo.
echo Avvio IDOMA 2.3.2 su http://127.0.0.1:8000
"%PYTHON%" -m uvicorn idoma_v2.server.main:app --host 0.0.0.0 --port 8000
pause
