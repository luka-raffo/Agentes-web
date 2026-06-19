@echo off
REM Expone el backend local (puerto 8000) a internet con ngrok.
REM Te imprime una URL publica https://xxxx.ngrok-free.app que tu web puede usar.
REM (El backend tiene que estar corriendo: ejecuta start.bat primero.)
cd /d "%~dp0"

if not exist ngrok.exe (
  echo No se encontro ngrok.exe en esta carpeta.
  echo.
  echo 1. Registrate gratis en https://ngrok.com
  echo 2. Descarga ngrok.exe para Windows desde el dashboard
  echo 3. Copia ngrok.exe a esta carpeta
  echo 4. Ejecuta una sola vez:  ngrok config add-authtoken TU_TOKEN
  echo.
  pause
  exit /b 1
)

echo Abriendo tunel hacia http://localhost:8000 ...
echo Copia la URL https://xxxx.ngrok-free.app que aparezca abajo.
ngrok.exe http 8000
pause
