@echo off
setlocal
title HealthMon Stop
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Server\scripts\runtime_menu.ps1" -Action Stop %*
exit /b %ERRORLEVEL%
