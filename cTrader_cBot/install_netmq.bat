@echo off
REM cTrader NetMQ Package Installer (Batch Wrapper)

cd /d "%~dp0"

echo Running NetMQ installer...
echo.

powershell -ExecutionPolicy Bypass -File "install_netmq.ps1"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Installation failed!
    pause
    exit /b 1
)

echo.
pause
