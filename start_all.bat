@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

echo ================================================================
echo demo2opt One-Click Start Script
echo ================================================================

call :resolve_python
if not defined PYTHON_EXE (
  echo [ERROR] No usable Python interpreter found.
  echo [HINT] Install Python or create .venv\Scripts\python.exe.
  pause
  exit /b 1
)
echo [INFO] Using Python: %PYTHON_EXE%

:: Check backend dependencies
"%PYTHON_EXE%" -c "import flask" >nul 2>nul
if %errorlevel% neq 0 (
  echo [WARN] Backend dependencies missing. Installing requirements...
  "%PYTHON_EXE%" -m pip install -r requirements.txt
)
"%PYTHON_EXE%" -c "import flask" >nul 2>nul
if %errorlevel% neq 0 (
  echo [ERROR] Failed to install backend dependencies.
  pause
  exit /b 1
)

:: Check Node.js and frontend dependencies
where npm >nul 2>nul
if %errorlevel% neq 0 (
  echo [ERROR] npm not found. Please install Node.js.
  pause
  exit /b 1
)

if not exist "frontend\node_modules" (
  echo [WARN] Frontend dependencies missing. Installing...
  pushd frontend
  call npm install
  popd
)

call :is_port_listening 5000
set "REST_BUSY=%errorlevel%"
call :is_port_listening 8001
set "WS_BUSY=%errorlevel%"
call :is_port_listening 4173
set "FE_BUSY=%errorlevel%"

echo.
echo [INFO] Service status before start:
if "%REST_BUSY%"=="0" (echo   REST 5000: already running) else (echo   REST 5000: stopped)
if "%WS_BUSY%"=="0"   (echo   WS   8001: already running) else (echo   WS   8001: stopped)
if "%FE_BUSY%"=="0"   (echo   FE   4173: already running) else (echo   FE   4173: stopped)
echo.

:: Backend startup logic
if "%REST_BUSY%"=="1" (
  if "%WS_BUSY%"=="1" (
    echo [INFO] Starting full backend stack REST + WS...
    start "demo2opt-backend" cmd /k ""%PYTHON_EXE%" scripts\start_web.py"
  ) else (
    echo [INFO] Starting REST server only...
    start "demo2opt-rest" cmd /k ""%PYTHON_EXE%" src\api\rest\server.py"
  )
) else (
  if "%WS_BUSY%"=="1" (
    echo [INFO] Starting WebSocket server only...
    start "demo2opt-ws" cmd /k ""%PYTHON_EXE%" src\api\ws\server.py 8001"
  )
)

:: Frontend startup logic
if "%FE_BUSY%"=="1" (
  echo [INFO] Starting frontend dev server...
  start "demo2opt-frontend" cmd /k "cd /d \"%CD%\frontend\" && npm run dev -- --host 127.0.0.1 --port 4173"
)

echo.
echo [SUCCESS] Start command dispatched.
echo Frontend: http://127.0.0.1:4173
echo REST API: http://127.0.0.1:5000
echo WebSocket: ws://127.0.0.1:8001
echo.
pause
exit /b 0

:resolve_python
set "PYTHON_EXE="

for %%P in (
  ".venv\Scripts\python.exe"
  "venv\Scripts\python.exe"
  "D:\APP\miniconda3\python.exe"
  "%USERPROFILE%\miniconda3\python.exe"
  "%USERPROFILE%\anaconda3\python.exe"
  "C:\ProgramData\Miniconda3\python.exe"
  "C:\ProgramData\Anaconda3\python.exe"
) do (
  if exist %%~P (
    call :check_python "%%~P"
    if defined PYTHON_EXE exit /b 0
  )
)

for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "$p=(Get-Process python -ErrorAction SilentlyContinue ^| Select-Object -First 1 -ExpandProperty Path); if($p){Write-Output $p}"`) do (
  if exist "%%P" (
    call :check_python "%%P"
    if defined PYTHON_EXE exit /b 0
  )
)

where python >nul 2>nul
if %errorlevel% equ 0 (
  for /f "delims=" %%P in ('where python') do (
    call :check_python "%%P"
    if defined PYTHON_EXE exit /b 0
  )
)

where python3 >nul 2>nul
if %errorlevel% equ 0 (
  for /f "delims=" %%P in ('where python3') do (
    call :check_python "%%P"
    if defined PYTHON_EXE exit /b 0
  )
)
exit /b 0

:check_python
"%~1" -c "import sys; print(sys.executable)" >nul 2>nul
if %errorlevel% neq 0 exit /b 1
set "PYTHON_EXE=%~1"
exit /b 0

:is_port_listening
set "PORT_BUSY="
for /f %%A in ('netstat -ano ^| findstr /R /C:":%~1 .*LISTENING"') do set "PORT_BUSY=1"
if defined PORT_BUSY (exit /b 0) else (exit /b 1)
