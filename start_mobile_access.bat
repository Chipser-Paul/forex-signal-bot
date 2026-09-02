@echo off
setlocal

REM Root of this repository
set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"
cd /d "%ROOT_DIR%"

set "PY_EXE=%ROOT_DIR%\dl_env\Scripts\python.exe"
set "ST_EXE=%ROOT_DIR%\dl_env\Scripts\streamlit.exe"
set "TAILSCALE_URL=http://paul.tail9b1221.ts.net:8501"
set "FOREX_REMOTE_ACCESS=1"

echo Starting mobile access (Tailscale mode)...
echo Target URL: %TAILSCALE_URL%
echo.

echo Checking Tailscale...
tailscale status >nul 2>nul
if errorlevel 1 (
  echo [WARN] Tailscale is not available in PATH.
  echo        Install/start Tailscale, then reconnect phone and laptop.
) else (
  echo [OK] Tailscale is available.
)

echo Starting Streamlit on port 8501...
if exist "%ST_EXE%" (
  start "Forex Streamlit" "%ST_EXE%" run frontend\app.py --server.address 0.0.0.0 --server.port 8501
) else if exist "%PY_EXE%" (
  start "Forex Streamlit" "%PY_EXE%" -m streamlit run frontend\app.py --server.address 0.0.0.0 --server.port 8501
) else (
  start "Forex Streamlit" python -m streamlit run frontend\app.py --server.address 0.0.0.0 --server.port 8501
)

echo.
echo Started.
echo 1) Keep the Streamlit window open.
echo 2) Ensure Tailscale is ON on laptop and phone.
echo 3) Open this URL in app/browser: %TAILSCALE_URL%
echo 4) Application-token and MT5 authentication are both required.
echo    HTTP transport is acceptable here only through the encrypted Tailscale path.
echo.
pause
