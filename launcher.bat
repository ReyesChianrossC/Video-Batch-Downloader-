@echo off
title Video Downloader - Web UI
color 0A

REM Get the directory where this batch file is located
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo ========================================
echo  Video Downloader - Web UI
echo ========================================
echo.

REM ── Dependency log check ─────────────────────────────────────────────────
set "LOG_FILE=dependency_check.log"
if exist "%LOG_FILE%" (
    findstr /C:"All dependencies are up to date v3" "%LOG_FILE%" >nul 2>&1
    if %errorlevel% equ 0 (
        echo Dependencies already verified - skipping checks...
        goto :run
    )
)

echo Checking dependencies...
echo.

REM ── Python ───────────────────────────────────────────────────────────────
echo [1/5] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Python is not installed or not in PATH!
    echo Please install Python from https://python.org
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)
python --version
echo       Python OK
echo.

REM ── pip ──────────────────────────────────────────────────────────────────
echo [2/5] Checking pip...
python -m pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: pip not found. Please reinstall Python.
    pause
    exit /b 1
)
echo       pip OK
echo.

REM ── yt-dlp ───────────────────────────────────────────────────────────────
echo [3/5] Checking yt-dlp...
python -c "import yt_dlp" >nul 2>&1
if %errorlevel% neq 0 (
    echo       Installing yt-dlp...
    python -m pip install yt-dlp
    if %errorlevel% neq 0 (
        echo ERROR: Failed to install yt-dlp. Check your internet connection.
        pause
        exit /b 1
    )
) else (
    echo       yt-dlp found - updating...
    python -m pip install --upgrade yt-dlp >nul 2>&1
    echo       yt-dlp OK
)
echo.

REM ── Flask ─────────────────────────────────────────────────────────────────
echo [4/5] Checking Flask...
python -c "import flask" >nul 2>&1
if %errorlevel% neq 0 (
    echo       Installing Flask...
    python -m pip install flask
    if %errorlevel% neq 0 (
        echo ERROR: Failed to install Flask. Check your internet connection.
        pause
        exit /b 1
    )
) else (
    echo       Flask OK
)
echo.

REM ── FFmpeg ────────────────────────────────────────────────────────────────
echo [5/5] Checking FFmpeg...
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo WARNING: FFmpeg is not installed or not in PATH!
    echo FFmpeg is required for muting B-roll videos.
    echo.
    echo Attempting to install FFmpeg using winget...
    winget install --id Gyan.FFmpeg -e --source winget --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo.
        echo ERROR: Automatic installation failed. 
        echo Please download FFmpeg manually from https://ffmpeg.org/download.html
        echo Extract it and add the 'bin' folder to your System PATH.
        echo.
        pause
    ) else (
        echo.
        echo FFmpeg installed successfully! 
        echo Relaunching automatically in 3 seconds to apply system PATH changes...
        timeout /t 3 /nobreak >nul
        explorer.exe "%~dpnx0"
        exit
    )
) else (
    echo       FFmpeg OK
)
echo.

REM ── Check required files ──────────────────────────────────────────────────
if not exist "app.py" (
    echo ERROR: app.py not found in %CD%
    echo Please ensure all files are present.
    pause
    exit /b 1
)

if not exist "auto_muter.py" (
    echo WARNING: auto_muter.py not found - B-roll muting will be skipped.
    echo.
)

REM ── Save dependency log ───────────────────────────────────────────────────
echo All dependencies are up to date v3 > "%LOG_FILE%"
echo All checks passed!
echo.

:run
echo ========================================
echo  Starting Video Downloader Web Server
echo ========================================
echo.
echo  The browser will open automatically.
echo  URL: http://localhost:5000
echo.
echo  ^^^>^^^> Close this window to stop the server ^^^<^^^<
echo.

REM Run the Flask app (blocking - keeps this window open as the kill switch)
python app.py

echo.
echo Server stopped.
echo.
pause
