@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Asistente Molecular Nanopore - Windows + WSL
cd /d "%~dp0"

echo ============================================================
echo  Asistente Molecular Nanopore - Windows + WSL
echo ============================================================
echo Carpeta Windows: %CD%
echo.

where wsl.exe >nul 2>nul
if errorlevel 1 goto :NO_WSL

wsl.exe --status >nul 2>nul
if errorlevel 1 goto :WSL_NOT_READY

for %%F in (app.py base_maestra.xlsx requirements.txt INICIAR_LINUX.sh) do (
  if not exist "%%F" (
    set "MISSING_FILE=%%F"
    goto :MISSING_FILE
  )
)

set "WSL_DIR="
for /f "usebackq delims=" %%I in (`wsl.exe wslpath -a -u "%CD%" 2^>nul`) do set "WSL_DIR=%%I"
if not defined WSL_DIR goto :PATH_ERROR

set "WSL_SCRIPT=%WSL_DIR%/INICIAR_LINUX.sh"
echo Carpeta WSL: %WSL_DIR%
echo.

rem Corrige finales de linea CRLF, frecuentes cuando el .sh se copia desde Windows.
wsl.exe sed -i "s/\r$//" "%WSL_SCRIPT%"
if errorlevel 1 goto :LINE_ENDING_ERROR

rem Abre el navegador solo cuando Streamlit responde.
start "" /b powershell.exe -NoProfile -WindowStyle Hidden -Command "$deadline=(Get-Date).AddMinutes(5); while((Get-Date) -lt $deadline){ try { $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost:8501/_stcore/health' -TimeoutSec 2; if($r.StatusCode -eq 200){ Start-Process 'http://localhost:8501'; exit 0 } } catch {}; Start-Sleep -Milliseconds 700 }; exit 1"

echo Iniciando INICIAR_LINUX.sh dentro de WSL...
echo No cierres esta ventana mientras uses la aplicacion.
echo.

rem Se entrega la ruta como argumento directo. No usa bash -lc ni comillas escapadas.
wsl.exe bash "%WSL_SCRIPT%"
set "APP_EXIT=%ERRORLEVEL%"

echo.
if "%APP_EXIT%"=="0" (
  echo La aplicacion termino normalmente.
) else (
  echo ERROR: La aplicacion termino con codigo %APP_EXIT%.
  echo Copia o toma una foto de todo el mensaje mostrado sobre esta linea.
)
echo.
pause
exit /b %APP_EXIT%

:MISSING_FILE
echo ERROR: falta %MISSING_FILE% en esta carpeta:
echo %CD%
goto :FAIL

:NO_WSL
echo ERROR: wsl.exe no esta instalado o no esta disponible.
echo Abre PowerShell como administrador y ejecuta: wsl --install -d Ubuntu
goto :FAIL

:WSL_NOT_READY
echo ERROR: WSL esta instalado, pero no hay una distribucion lista para ejecutar.
echo Ejecuta en PowerShell: wsl -l -v
echo Si Ubuntu no aparece, ejecuta como administrador: wsl --install -d Ubuntu
echo Luego abre Ubuntu una vez y crea el usuario Linux.
goto :FAIL

:PATH_ERROR
echo ERROR: WSL no pudo convertir esta ruta de Windows:
echo %CD%
echo Mueve temporalmente la carpeta a una ruta simple, por ejemplo C:\AsistenteMolecular
goto :FAIL

:LINE_ENDING_ERROR
echo ERROR: no se pudo preparar INICIAR_LINUX.sh dentro de WSL.
echo Ruta calculada: %WSL_SCRIPT%
goto :FAIL

:FAIL
echo.
echo El lanzador se detuvo antes de iniciar Streamlit.
echo Copia o toma una foto de este mensaje.
echo.
pause
exit /b 1
