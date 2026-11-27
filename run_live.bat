@echo off
REM Launch script for Live Stream mode with HTTPS (Windows)
REM Handles paths with spaces and parentheses

echo ==========================================
echo Fabric Defect Detection - Live Stream Mode
echo ==========================================
echo.

REM Get the script directory (absolute path, handles spaces)
set "SCRIPT_DIR=%~dp0"

REM Remove trailing backslash if present
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

REM Define certificate paths (absolute, quoted)
set "CERT_DIR=%SCRIPT_DIR%\certs"
set "CERT_FILE=%CERT_DIR%\cert.pem"
set "KEY_FILE=%CERT_DIR%\key.pem"

REM Check if virtual environment exists
if not exist "%SCRIPT_DIR%\venv\" (
    echo Virtual environment not found. Creating one...
    python -m venv "%SCRIPT_DIR%\venv"
    if errorlevel 1 goto :error_venv
    echo Virtual environment created.
    echo.
)

REM Activate virtual environment
echo Activating virtual environment...
call "%SCRIPT_DIR%\venv\Scripts\activate.bat"
if errorlevel 1 goto :error_activate

REM Check if dependencies are installed (including cryptography)
python -c "import fastapi, cryptography" 2>nul
if errorlevel 1 goto :install_deps
goto :deps_ok

:install_deps
echo Dependencies not installed. Installing from requirements.txt...
python -m pip install --upgrade pip
pip install -r "%SCRIPT_DIR%\requirements.txt"
if errorlevel 1 goto :error_deps
echo Dependencies installed.
echo.

:deps_ok

REM Generate or check certificate
echo Checking SSL certificate...
python "%SCRIPT_DIR%\generate_cert.py"
set CERT_EXIT_CODE=%errorlevel%

if not exist "%CERT_FILE%" goto :error_cert
if not exist "%KEY_FILE%" goto :error_cert

echo.
echo ==========================================
echo SSL Certificate Ready
echo ==========================================
echo.

REM Launch the FastAPI server with HTTPS
echo Starting HTTPS server for live stream...
echo.
echo Server URLs:
echo   Laptop dashboard:  https://localhost:8443
echo.

if %CERT_EXIT_CODE%==0 (
    echo   Phone link will be shown in the Live Stream tab
    echo   ^(uses your LAN IP address^)
) else (
    echo   WARNING: No network detected!
    echo   Connect to Wi-Fi and restart to get phone link.
)

echo.
echo Windows Firewall:
echo   If the phone cannot reach the laptop, run this ONCE
echo   in an Administrator PowerShell:
echo.
echo   netsh advfirewall firewall add rule name="FabricLive8443" ^
dir=in action=allow protocol=TCP localport=8443 profile=private
echo.
echo   Also ensure the network is set to "Private" in Windows settings.
echo.
echo Press Ctrl+C to stop the server
echo ==========================================
echo.

REM Change to backend directory
cd /d "%SCRIPT_DIR%\backend"
if errorlevel 1 goto :error_cd

REM Start server (no --reload to avoid file watcher issues with spaces in path)
python -m uvicorn main:app --host 0.0.0.0 --port 8443 --ssl-keyfile "%KEY_FILE%" --ssl-certfile "%CERT_FILE%"
goto :end

:error_venv
echo ERROR: Failed to create virtual environment
echo Make sure Python 3.10+ is installed and in PATH
pause
exit /b 1

:error_activate
echo ERROR: Failed to activate virtual environment
pause
exit /b 1

:error_deps
echo ERROR: Failed to install dependencies
pause
exit /b 1

:error_cert
echo ERROR: SSL certificate generation failed
echo Certificate files not found at:
echo   %CERT_FILE%
echo   %KEY_FILE%
pause
exit /b 1

:error_cd
echo ERROR: Failed to change to backend directory
pause
exit /b 1

:end
