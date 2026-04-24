@echo off
setlocal enabledelayedexpansion
title JARVIS HUD - Build

REM Always run from the folder this BAT file is in
cd /d "%~dp0"

echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║       J.A.R.V.I.S HUD v3 - Build            ║
echo  ╚══════════════════════════════════════════════╝
echo.

REM ── Check Python ──────────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found on PATH.
    echo         Download from https://python.org
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do echo [OK] %%i

REM ── Check required files ──────────────────────────────────────
if not exist jarvis.spec (
    echo [ERROR] jarvis.spec not found in:
    echo         %CD%
    pause
    exit /b 1
)

if not exist jarvis.cfg (
    echo [WARNING] jarvis.cfg not found in:
    echo           %CD%
)

REM ── Create venv ───────────────────────────────────────────────
echo.
echo [1/5] Creating isolated virtual environment...
if exist .venv rmdir /s /q .venv
python -m venv .venv
if %errorlevel% neq 0 (
    echo [ERROR] venv creation failed.
    pause
    exit /b 1
)

REM ── Activate venv ─────────────────────────────────────────────
call .venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo [ERROR] Failed to activate virtual environment.
    pause
    exit /b 1
)

REM ── Upgrade pip ───────────────────────────────────────────────
echo [2/5] Upgrading pip...
python -m pip install --upgrade pip --quiet
if %errorlevel% neq 0 (
    echo [ERROR] pip upgrade failed.
    pause
    exit /b 1
)

REM ── Install dependencies ──────────────────────────────────────
echo [3/5] Installing dependencies...
pip install -r requirements.txt --quiet

if %errorlevel% neq 0 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
)
echo [OK] Dependencies installed.

REM ── Build ─────────────────────────────────────────────────────
echo [4/5] Building JARVIS.exe...
python -m PyInstaller jarvis.spec --clean --noconfirm

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] PyInstaller build failed.
    echo         Working folder: %CD%
    echo         Check the output above for details.
    pause
    exit /b 1
)

REM ── Copy config next to exe ───────────────────────────────────
echo [5/5] Finalising output...
if not exist dist mkdir dist

if exist jarvis.cfg (
    copy /y jarvis.cfg dist\jarvis.cfg >nul
    echo [OK] Config copied to dist\jarvis.cfg
) else (
    echo [WARNING] jarvis.cfg was not copied because it was not found.
)

REM ── Done ──────────────────────────────────────────────────────
echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║  BUILD COMPLETE                             ║
echo  ║                                              ║
echo  ║  Output:   dist\JARVIS.exe                  ║
echo  ║  Config:   dist\jarvis.cfg                  ║
echo  ║                                              ║
echo  ║  To run:                                     ║
echo  ║    1. Start OpenClaw on port 8000            ║
echo  ║    2. Double-click dist\JARVIS.exe           ║
echo  ║    3. HUD opens at http://localhost:7474     ║
echo  ║                                              ║
echo  ║  Kiosk mode (no browser UI):                 ║
echo  ║    Set kiosk_mode = true in jarvis.cfg       ║
echo  ╚══════════════════════════════════════════════╝
echo.
pause