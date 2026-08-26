@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo  Asistente Molecular Nanopore V10.4 - Windows + WSL
echo ============================================================

where wsl.exe >nul 2>nul
if errorlevel 1 (
  echo ERROR: WSL no esta instalado o no esta disponible.
  pause
  exit /b 1
)

for %%F in (app.py base_maestra.xlsx requirements.txt INICIAR_LINUX.sh) do (
  if not exist "%%F" (
    echo ERROR: falta %%F en esta carpeta.
    pause
    exit /b 1
  )
)

for /f "usebackq delims=" %%I in (`wsl.exe wslpath -a "%CD%"`) do set "WSL_DIR=%%I"
if not defined WSL_DIR (
  echo ERROR: No se pudo convertir la ruta de Windows a WSL.
  pause
  exit /b 1
)

echo Carpeta del proyecto: %WSL_DIR%
echo El entorno Python y la cache se guardaran dentro de Linux para acelerar el inicio.
echo.

rem Espera hasta que Streamlit responda y recien entonces abre el navegador de Windows.
start "" /b powershell.exe -NoProfile -WindowStyle Hidden -Command "$deadline=(Get-Date).AddMinutes(3); while((Get-Date) -lt $deadline){ try { $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost:8501/_stcore/health' -TimeoutSec 2; if($r.StatusCode -eq 200){ Start-Process 'http://localhost:8501'; exit } } catch {}; Start-Sleep -Milliseconds 500 }"

echo Iniciando servidor en WSL. No cierres esta ventana mientras uses la app.
wsl.exe bash -lc "cd \"%WSL_DIR%\" && chmod +x INICIAR_LINUX.sh && ./INICIAR_LINUX.sh"

if errorlevel 1 (
  echo.
  echo La aplicacion termino con un error. Revisa el mensaje anterior.
  pause
)
endlocal
