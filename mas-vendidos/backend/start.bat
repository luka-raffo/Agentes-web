@echo off
REM Levanta el backend FastAPI en http://localhost:8000
cd /d "%~dp0"
echo Iniciando backend en http://localhost:8000  (Ctrl+C para detener)
py -m uvicorn api:app --host 0.0.0.0 --port 8000
pause
