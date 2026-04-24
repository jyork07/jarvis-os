@echo off
set "SCRIPT=%~dp0dist\Launch-JARVIS-Stack.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
pause
