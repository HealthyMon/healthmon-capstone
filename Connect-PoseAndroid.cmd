@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Ai\Pose\android-device.ps1" -Action connect %*
set "poseExit=%ERRORLEVEL%"
if not "%poseExit%"=="0" pause
exit /b %poseExit%
