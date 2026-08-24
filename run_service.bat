@echo off
title KVIE Local Streaming STT Service
echo ===================================================
echo   Kritix Voice Intelligence Engine (KVIE) Service
echo   Starting WebSocket Streaming STT on port 8765...
echo ===================================================
echo.

if exist .venv\Scripts\activate (
    call .venv\Scripts\activate
) else (
    if exist venv\Scripts\activate (
        call venv\Scripts\activate
    )
)

python -m Backend.kvie.service
pause
