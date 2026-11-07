@echo off
title VisionAttend-AI Launcher
color 0b

echo =======================================================
echo          Starting VisionAttend-AI Services
echo =======================================================
echo.

set ROOT_DIR=%~dp0

:: Check if PostgreSQL service is running (optional safety start)
echo [1/3] Checking PostgreSQL Service...
sc query postgresql-x64-17 | find "RUNNING" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Attempting to start PostgreSQL service...
    net start postgresql-x64-17 >nul 2>&1
) else (
    echo [OK] PostgreSQL service is running.
)

:: Start Backend (FastAPI)
echo [2/3] Launching FastAPI Backend on http://0.0.0.0:8000 ...
start "VisionAttend-AI - Backend (FastAPI)" cmd /k "cd /d "%ROOT_DIR%backend" && if exist .venv\Scripts\activate.bat (call .venv\Scripts\activate.bat) && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

:: Start Frontend (Next.js)
echo [3/3] Launching Next.js Frontend on http://localhost:3000 ...
start "VisionAttend-AI - Frontend (Next.js)" cmd /k "cd /d "%ROOT_DIR%frontend" && npm run dev"

echo.
echo =======================================================
echo All services launched!
echo.
echo   - Backend API:       http://localhost:8000
echo   - Swagger Docs:      http://localhost:8000/docs
echo   - Frontend Admin:    http://localhost:3000
echo =======================================================
echo.
echo Opening Frontend in default web browser in 5 seconds...
timeout /t 5 >nul
start http://localhost:3000

echo.
echo Both terminal windows are running in the background.
echo You can safely close this launcher window at any time.
pause
