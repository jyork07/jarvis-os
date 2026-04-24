@echo off
set "SCRIPT=%~dp0Launch-JARVIS-Stack.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
pause
