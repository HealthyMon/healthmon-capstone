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
set "llm_failed=0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Qwen4B.ps1" -LlmOnly
if errorlevel 1 (
    set "llm_failed=1"
    echo Qwen4B LLM is unavailable. Continuing with the common server and food AI.
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Server\scripts\local_server.ps1" -Action Start -NoOpen
set "healthmon_exit=%ERRORLEVEL%"
if "%healthmon_exit%"=="0" (
    if exist "%~dp0.runtime\local-server-connection.html" (
        start "" "%~dp0.runtime\local-server-connection.html"
    ) else (
        echo Server started, but the connection guide was not generated.
    )
)
echo.
if "%llm_failed%"=="1" (
    echo Dialogue is NOT ready. Fix the Qwen4B startup error above and run this launcher again.
    set "healthmon_exit=1"
)
pause
exit /b %healthmon_exit%
