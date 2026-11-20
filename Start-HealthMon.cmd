@echo off
setlocal
title HealthMon Local Server
echo Starting your configured HealthMon server. Existing data is preserved.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Server\scripts\start_food_server.ps1"
if errorlevel 1 (
    echo Food AI server startup failed. See the message above.
    pause
    exit /b 1
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Qwen4B.ps1" -LlmOnly
if errorlevel 1 (
    echo Qwen4B LLM server startup failed. See the message above.
    pause
    exit /b 1
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Server\scripts\local_server.ps1" -Action Start
set "healthmon_exit=%ERRORLEVEL%"
echo.
pause
exit /b %healthmon_exit%
