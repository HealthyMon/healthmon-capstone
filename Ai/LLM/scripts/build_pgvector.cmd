@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 exit /b 1
set "PGROOT=E:\qwen-llm\runtime\pgsql"
cd /d E:\qwen-llm\runtime\pgvector
nmake /F Makefile.win
if errorlevel 1 exit /b 1
nmake /F Makefile.win install
