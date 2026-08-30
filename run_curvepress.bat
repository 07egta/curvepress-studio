@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem Reuse an already-running local server when possible.
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 http://127.0.0.1:8765/api/health | Out-Null; exit 0 } catch { exit 1 }"
if not errorlevel 1 goto open_window

rem The Windows one-click bundle carries a portable Python/CAD runtime.
rem Source checkouts can still use the local venv or an installed Python.
set "PYTHON_EXE="
if exist "%~dp0runtime\python.exe" set "PYTHON_EXE=%~dp0runtime\python.exe"
if not defined PYTHON_EXE if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"

if not defined PYTHON_EXE (
  py -3 -m venv .venv
  if errorlevel 1 (
    echo Python 3.11 or newer is required for a source checkout.
    pause
    exit /b 1
  )
  .venv\Scripts\python.exe -m pip install -e ".[cad]"
  if errorlevel 1 (
    echo Installation failed. Check your internet connection and try again.
    pause
    exit /b 1
  )
  set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
)

start "CurvePress server" /min "%PYTHON_EXE%" -m curvepress serve --no-browser
for /l %%I in (1,1,30) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 http://127.0.0.1:8765/api/health | Out-Null; exit 0 } catch { exit 1 }"
  if not errorlevel 1 goto open_window
  timeout /t 1 /nobreak >nul
)
echo CurvePress did not start within 30 seconds.
pause
exit /b 1

:open_window
set "BROWSER="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "BROWSER=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined BROWSER if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "BROWSER=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined BROWSER if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" set "BROWSER=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not defined BROWSER if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" set "BROWSER=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if defined BROWSER (
  start "CurvePress Studio" "%BROWSER%" --app=http://127.0.0.1:8765 --window-position=0,0 --window-size=1280,900
) else (
  start "" http://127.0.0.1:8765
)

