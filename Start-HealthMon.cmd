@echo off
setlocal
title HealthMon Start
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Server\scripts\runtime_menu.ps1" -Action Start %*
exit /b %ERRORLEVEL%
