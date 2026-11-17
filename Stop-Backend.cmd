@echo off
setlocal
title HealthMon Backend
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Server\scripts\local_server.ps1" -Action Stop -Target Backend
set "healthmon_exit=%ERRORLEVEL%"
pause
exit /b %healthmon_exit%
