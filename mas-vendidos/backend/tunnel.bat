@echo off
REM Expone el backend local (puerto 8000) a internet con un tunel Cloudflare.
REM Te imprime una URL publica https://....trycloudflare.com que tu web puede usar.
REM (El backend tiene que estar corriendo: ejecuta start.bat primero.)
cd /d "%~dp0"

if not exist cloudflared.exe (
  echo No se encontro cloudflared.exe en esta carpeta.
  echo Descargalo de: https://github.com/cloudflare/cloudflared/releases
  echo  ^(archivo cloudflared-windows-amd64.exe, renombralo a cloudflared.exe^)
  pause
  exit /b 1
)

echo Abriendo tunel hacia http://localhost:8000 ...
echo Copia la URL https://....trycloudflare.com que aparezca abajo.
cloudflared.exe tunnel --url http://localhost:8000
pause
