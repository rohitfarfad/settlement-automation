@echo off
setlocal enabledelayedexpansion

title Prestige Valero Repair

set "PROJECT_ROOT=C:\CC Automation\settlement-automation"
set "REPAIR_SCRIPT=%PROJECT_ROOT%\scripts\repair_valero_2026_07_10.ps1"
set "LOG_DIR=%PROJECT_ROOT%\output\logs"

echo.
echo ============================================================
echo PRESTIGE VALERO REPAIR
echo ============================================================
echo.
echo This will update the automation code and repair the Valero workbook.
echo Please make sure Excel is closed before continuing.
echo.
pause

if not exist "%PROJECT_ROOT%" (
    echo.
    echo FAILED: Project folder was not found:
    echo %PROJECT_ROOT%
    echo.
    pause
    exit /b 1
)

cd /d "%PROJECT_ROOT%"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo.
echo Checking Git...
echo.

git --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo FAILED: Git is not installed or not available from this computer.
    echo Please tell Rohit: Git was not found.
    echo.
    pause
    exit /b 1
)

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo.
    echo FAILED: This folder is not a valid Git repository:
    echo %PROJECT_ROOT%
    echo.
    pause
    exit /b 1
)

echo.
echo Backing up local .env file if present...
echo.

set "ENV_BACKUP=%TEMP%\prestige_settlement_env_backup_%RANDOM%_%RANDOM%.bak"

if exist "%PROJECT_ROOT%\.env" (
    copy /Y "%PROJECT_ROOT%\.env" "%ENV_BACKUP%" >nul
    if errorlevel 1 (
        echo.
        echo FAILED: Could not backup .env file.
        echo Please tell Rohit: .env backup failed.
        echo.
        pause
        exit /b 1
    )
    echo .env backup created.
) else (
    echo No .env file found to backup.
)

echo.
echo Saving any local code changes to Git stash...
echo.

git stash push -m "auto-stash before Prestige Valero repair" >nul 2>&1
echo Git stash step complete. If there were no local changes, this is normal.

echo.
echo Updating code from GitHub...
echo.

git fetch --all --prune
if errorlevel 1 (
    echo.
    echo FAILED: Could not fetch latest code from GitHub.
    echo Please tell Rohit: git fetch failed.
    echo.
    pause
    exit /b 1
)

set "TARGET_REF="

for /f "delims=" %%U in ('git rev-parse --abbrev-ref --symbolic-full-name @{u} 2^>nul') do (
    set "TARGET_REF=%%U"
)

if "%TARGET_REF%"=="" (
    for /f "delims=" %%D in ('git symbolic-ref --short refs/remotes/origin/HEAD 2^>nul') do (
        set "TARGET_REF=%%D"
    )
)

if "%TARGET_REF%"=="" (
    set "TARGET_REF=origin/main"
)

echo Updating local code to match: %TARGET_REF%
git reset --hard "%TARGET_REF%"
if errorlevel 1 (
    echo.
    echo FAILED: Could not reset code to latest GitHub version.
    echo Please tell Rohit: git reset failed.
    echo.
    pause
    exit /b 1
)

if exist "%ENV_BACKUP%" (
    echo.
    echo Restoring .env file...
    copy /Y "%ENV_BACKUP%" "%PROJECT_ROOT%\.env" >nul
    if errorlevel 1 (
        echo.
        echo FAILED: Could not restore .env file.
        echo Please tell Rohit: .env restore failed.
        echo.
        pause
        exit /b 1
    )
)

if not exist "%REPAIR_SCRIPT%" (
    echo.
    echo FAILED: Repair script was not found after updating the code:
    echo %REPAIR_SCRIPT%
    echo.
    echo Please tell Rohit: repair_valero_2026_07_10.ps1 was not found.
    echo.
    pause
    exit /b 1
)

echo.
echo Starting repair...
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%REPAIR_SCRIPT%"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo ============================================================
if "%EXIT_CODE%"=="0" (
    echo REPAIR COMPLETED SUCCESSFULLY
    echo Please tell Rohit: REPAIR COMPLETED SUCCESSFULLY
) else (
    echo REPAIR FAILED
    echo Please send Rohit the latest log file:
    echo %PROJECT_ROOT%\output\logs\manual_valero_repair_latest.log
)
echo ============================================================
echo.

pause
exit /b %EXIT_CODE%