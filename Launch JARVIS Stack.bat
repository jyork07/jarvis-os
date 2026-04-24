@echo off
set "SCRIPT=%~dp0dist\Launch-JARVIS-Stack.ps1"
start "" powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%SCRIPT%"
exit /b 0
