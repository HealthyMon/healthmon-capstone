@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Ai\Pose\pose-runtime.ps1" -Action setup
exit /b %ERRORLEVEL%
