@echo off
setlocal
title HealthMon Local Server
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Server\scripts\local_server.ps1" -Action Start
set "healthmon_exit=%ERRORLEVEL%"
echo.
pause
exit /b %healthmon_exit%
