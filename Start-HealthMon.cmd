@echo off
setlocal EnableExtensions DisableDelayedExpansion
title HealthMon Start
echo HealthMon - Start
set "HEALTHMON_CMD_LAUNCH=1"
set "HealthMonPowerShell=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%~dp0Server\scripts\runtime_menu.ps1" goto missing_menu
if not exist "%HealthMonPowerShell%" goto missing_shell
"%HealthMonPowerShell%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Server\scripts\runtime_menu.ps1" -Action Start %*
set "HealthMonExit=%ERRORLEVEL%"
if "%HealthMonExit%"=="0" exit /b 0
echo.
echo [ERROR] HealthMon could not complete the command. Exit code: %HealthMonExit%
echo Read the error above. Administrator mode is not required by this launcher.
goto failed

:missing_menu
set "HealthMonExit=2"
echo.
echo [ERROR] Required menu script is missing:
echo "%~dp0Server\scripts\runtime_menu.ps1"
echo Extract the ENTIRE develop ZIP first. Keep the CMD and Server folder together.
goto failed

:missing_shell
set "HealthMonExit=3"
echo.
echo [ERROR] Windows PowerShell was not found:
echo "%HealthMonPowerShell%"
echo Check Windows PowerShell availability on this PC.

:failed
echo Keep this error message when reporting the problem.
for %%A in (%*) do if /I "%%~A"=="-NoPause" exit /b %HealthMonExit%
pause
exit /b %HealthMonExit%
