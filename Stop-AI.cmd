@echo off
setlocal
title HealthMon AI
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Server\scripts\local_server.ps1" -Action Stop -Target AI
set "healthmon_exit=%ERRORLEVEL%"
pause
exit /b %healthmon_exit%
