@echo off
title Kritix Voice Intelligence Engine (KVIE)
echo ===================================================
echo   Kritix Voice Intelligence Engine (KVIE) Launcher
echo ===================================================
echo.

echo [1/2] Launching KVIE Streaming STT Background Service...
start "KVIE Streaming STT Service" /min cmd /c "if exist .venv\Scripts\activate (call .venv\Scripts\activate) else (if exist venv\Scripts\activate (call venv\Scripts\activate)) & python -m Backend.kvie.service"

timeout /t 2 /nobreak >nul

echo [2/2] Launching KVIE Desktop Workspace (Tauri)...
npm run tauri:dev

pause
