@echo off
REM Polymarket Trading Bot Startup Script (Windows)

setlocal enabledelayedexpansion

echo.
echo ╔════════════════════════════════════════════════════════════╗
echo ║   Polymarket Trading Bot Dashboard                         ║
echo ║   Starting bot with API server and notifications...        ║
echo ╚════════════════════════════════════════════════════════════╝
echo.

REM Load .env file if it exists OR replace with config.yaml
if exist .env (
    echo [*] Loading environment from .env
    for /f "delims== tokens=1,*" %%a in (.env) do (
        if not "%%a"=="" if not "%%a:~0,1%%" == "#" (
            set "%%a=%%b"
        )
    )
)


REM Check if --paper flag is passed
set "PAPER_MODE="
if "%1"=="--paper" (
    set "PAPER_MODE=--paper"
    echo [*] Running in PAPER MODE (no real USDC will be spent)
) else (
    echo.
    echo ⚠️  WARNING: Running in LIVE MODE
    echo This will spend real USDC on Polymarket!
    echo.
    set /p confirm="Type 'yes' to continue: "
    if not "!confirm!"=="yes" (
        echo Aborted.
        exit /b 1
    )
)

echo.
echo [*] Starting API server on http://0.0.0.0:8000
echo [*] Terminal UI running alongside
echo [*] Open http://localhost:8000 in browser for dashboard
echo [*] (Or visit http://localhost:5173 if npm run dev is running in web/)
echo.

REM Run the bot
python apps/trend_bot.py %PAPER_MODE%
