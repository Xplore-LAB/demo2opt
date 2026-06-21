@echo off
setlocal

set "PORT=4176"
set "ROOT_DIR=%~dp0"
set "DIST_DIR=%ROOT_DIR%dist"

if not exist "%DIST_DIR%\index.html" (
  echo [ERROR] dist\index.html not found.
  echo Please make sure the built frontend files exist in:
  echo %DIST_DIR%
  pause
  exit /b 1
)

where py >nul 2>nul
if %errorlevel%==0 (
  set "PY_CMD=py"
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    set "PY_CMD=python"
  ) else (
    echo [ERROR] Python was not found.
    echo Please install Python, or run this on a machine with Python available.
    pause
    exit /b 1
  )
)

echo Starting Nitrogen Vue dist server...
echo Dist path: %DIST_DIR%
echo URL: http://127.0.0.1:%PORT%

start "Nitrogen Vue Dist Server" cmd /k "cd /d ""%DIST_DIR%"" && %PY_CMD% -m http.server %PORT%"
timeout /t 2 >nul
start "" "http://127.0.0.1:%PORT%"

echo Browser opened. You can close this window.
exit /b 0
