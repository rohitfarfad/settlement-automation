[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

# ==============================================================================
# ONE-TIME VALERO REPAIR - JULY 2026
# ==============================================================================
# This script:
# 1. Backs up Valero workbooks.
# 2. Clears Valero workbook entries for 2026-07-08 through 2026-07-09.
# 3. Reprocesses Valero report dated 2026-07-09 without notification.
# 4. Reprocesses Valero report dated 2026-07-10 with notification.
# ==============================================================================

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$WorkbookRoot = "P:\AUTOMATED_CC_WORKBOOKS"

$Supplier = "valero"
$EraseStartDate = "2026-07-08"
$EraseEndDate = "2026-07-09"
$ReprocessDate1 = "2026-07-09"
$ReprocessDate2 = "2026-07-10"

Set-Location $ProjectRoot

$LogDir = Join-Path $ProjectRoot "output\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir "manual_valero_repair_$Timestamp.log"
$LatestLogFile = Join-Path $LogDir "manual_valero_repair_latest.log"

$RepairRoot = Join-Path $ProjectRoot "data\manual_repairs\valero_2026_07_10_$Timestamp"
$TempWorkbookRoot = Join-Path $RepairRoot "valero_workbooks_to_clear"
$BackupRoot = Join-Path $RepairRoot "original_valero_backups"
$ClearOutputRoot = Join-Path $RepairRoot "clear_script_output"

New-Item -ItemType Directory -Force -Path $RepairRoot | Out-Null
New-Item -ItemType Directory -Force -Path $TempWorkbookRoot | Out-Null
New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
New-Item -ItemType Directory -Force -Path $ClearOutputRoot | Out-Null

function Write-Log {
    param([string]$Message)

    $Line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
    $Line | Tee-Object -FilePath $LogFile -Append
}

function Complete-WithFailure {
    param([string]$Message)

    Write-Log ""
    Write-Log "================================================================================"
    Write-Log "REPAIR FAILED"
    Write-Log "================================================================================"
    Write-Log $Message
    Write-Log ""
    Write-Log "Please send this log file to Rohit:"
    Write-Log $LogFile

    Copy-Item -Path $LogFile -Destination $LatestLogFile -Force -ErrorAction SilentlyContinue

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Red
    Write-Host "REPAIR FAILED" -ForegroundColor Red
    Write-Host "============================================================" -ForegroundColor Red
    Write-Host $Message -ForegroundColor Red
    Write-Host ""
    Write-Host "Please send Rohit this log file:"
    Write-Host $LogFile
    Write-Host ""

    Read-Host "Press ENTER to close this window"
    exit 1
}

function Invoke-LoggedCommand {
    param(
        [string]$StepName,
        [string]$Executable,
        [string[]]$Arguments
    )

    Write-Log ""
    Write-Log "STEP: $StepName"
    Write-Log "--------------------------------------------------------------------------------"
    Write-Log "Command: $Executable $($Arguments -join ' ')"

    & $Executable @Arguments *>&1 | Tee-Object -FilePath $LogFile -Append

    $ExitCode = $LASTEXITCODE

    if ($ExitCode -ne 0) {
        Complete-WithFailure "$StepName failed with exit code $ExitCode."
    }

    Write-Log "STEP COMPLETE: $StepName"
}

try {
    $PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    $ClearScript = Join-Path $ProjectRoot "scripts\clear_excel_entries.py"
    $RunDailyScript = Join-Path $ProjectRoot "scripts\run_daily.py"

    Write-Log "MANUAL VALERO REPAIR STARTED"
    Write-Log "================================================================================"
    Write-Log "Project root       : $ProjectRoot"
    Write-Log "Workbook root      : $WorkbookRoot"
    Write-Log "Supplier           : $Supplier"
    Write-Log "Erase date range   : $EraseStartDate through $EraseEndDate"
    Write-Log "Reprocess date 1   : $ReprocessDate1"
    Write-Log "Reprocess date 2   : $ReprocessDate2"
    Write-Log "Repair root        : $RepairRoot"
    Write-Log "Log file           : $LogFile"

    if (-not (Test-Path $ProjectRoot)) {
        Complete-WithFailure "Project folder was not found: $ProjectRoot"
    }

    if (-not (Test-Path $WorkbookRoot)) {
        Complete-WithFailure "Workbook shared folder was not found: $WorkbookRoot. Make sure the P: drive is connected."
    }

    if (-not (Test-Path $PythonExe)) {
        Complete-WithFailure "Python executable was not found: $PythonExe"
    }

    if (-not (Test-Path $ClearScript)) {
        Complete-WithFailure "Clear script was not found: $ClearScript"
    }

    if (-not (Test-Path $RunDailyScript)) {
        Complete-WithFailure "Daily script was not found: $RunDailyScript"
    }

    Write-Log ""
    Write-Log "STEP: Find Valero workbooks"
    Write-Log "--------------------------------------------------------------------------------"

    $ValeroWorkbooks = Get-ChildItem -Path $WorkbookRoot -Filter "*.xlsx" -File -Recurse |
        Where-Object {
            $_.Name -notlike "~$*" -and
            $_.Name -match "(?i)VALERO"
        }

    if ($ValeroWorkbooks.Count -eq 0) {
        Write-Log "No workbooks matching '*VALERO*.xlsx' were found."
        Write-Log "Available workbook files:"
        Get-ChildItem -Path $WorkbookRoot -Filter "*.xlsx" -File -Recurse |
            Select-Object -ExpandProperty FullName |
            Tee-Object -FilePath $LogFile -Append

        Complete-WithFailure "No Valero workbooks were found. The script stopped before changing any workbook."
    }

    $DuplicateNames = $ValeroWorkbooks |
        Group-Object Name |
        Where-Object { $_.Count -gt 1 }

    if ($DuplicateNames.Count -gt 0) {
        Write-Log "Duplicate Valero workbook filenames were found in different folders:"
        $DuplicateNames | ForEach-Object {
            Write-Log "Duplicate name: $($_.Name)"
        }

        Complete-WithFailure "Duplicate Valero workbook filenames found. The script stopped to avoid copying back to the wrong file."
    }

    Write-Log "Valero workbooks found: $($ValeroWorkbooks.Count)"
    $ValeroWorkbooks | ForEach-Object {
        Write-Log "  $($_.FullName)"
    }

    Write-Log ""
    Write-Log "STEP: Backup and stage Valero workbooks"
    Write-Log "--------------------------------------------------------------------------------"

    $WorkbookMap = @{}

    foreach ($Workbook in $ValeroWorkbooks) {
        $OriginalPath = $Workbook.FullName
        $FileName = $Workbook.Name

        $BackupPath = Join-Path $BackupRoot $FileName
        $TempPath = Join-Path $TempWorkbookRoot $FileName

        Copy-Item -Path $OriginalPath -Destination $BackupPath -Force
        Copy-Item -Path $OriginalPath -Destination $TempPath -Force

        $WorkbookMap[$FileName] = $OriginalPath

        Write-Log "Backed up and staged: $FileName"
    }

    Write-Log "Backup folder: $BackupRoot"

    Invoke-LoggedCommand `
        -StepName "Clear Valero staged workbook entries for July 8 and July 9" `
        -Executable $PythonExe `
        -Arguments @(
            $ClearScript,
            "--workbook-root", $TempWorkbookRoot,
            "--output-root", $ClearOutputRoot,
            "--start-date", $EraseStartDate,
            "--end-date", $EraseEndDate,
            "--write",
            "--write-originals"
        )

    Write-Log ""
    Write-Log "STEP: Copy cleared Valero workbooks back to shared folder"
    Write-Log "--------------------------------------------------------------------------------"

    foreach ($FileName in $WorkbookMap.Keys) {
        $ClearedPath = Join-Path $TempWorkbookRoot $FileName
        $OriginalPath = $WorkbookMap[$FileName]

        if (-not (Test-Path $ClearedPath)) {
            Complete-WithFailure "Cleared workbook was not found: $ClearedPath"
        }

        Copy-Item -Path $ClearedPath -Destination $OriginalPath -Force
        Write-Log "Updated original workbook: $OriginalPath"
    }

    Invoke-LoggedCommand `
        -StepName "Reprocess Valero report dated July 9 without notification" `
        -Executable $PythonExe `
        -Arguments @(
            $RunDailyScript,
            "--suppliers", "valero",
            "--report-date", $ReprocessDate1,
            "--write-excel",
            "--write-originals"
        )

    Invoke-LoggedCommand `
        -StepName "Reprocess Valero report dated July 10 with notification" `
        -Executable $PythonExe `
        -Arguments @(
            $RunDailyScript,
            "--suppliers", "valero",
            "--report-date", $ReprocessDate2,
            "--write-excel",
            "--write-originals",
            "--notify"
        )

    $SuccessFile = Join-Path $ProjectRoot "REPAIR_COMPLETED_SUCCESSFULLY.txt"

    @"
MANUAL VALERO REPAIR COMPLETED SUCCESSFULLY

Completed at: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')

Actions completed:
- Valero workbooks backed up.
- Valero entries cleared for $EraseStartDate through $EraseEndDate.
- Valero report $ReprocessDate1 reprocessed and written.
- Valero report $ReprocessDate2 reprocessed, written, and notification sent.

Log file:
$LogFile

Backup folder:
$BackupRoot
"@ | Set-Content -Path $SuccessFile -Encoding UTF8

    Write-Log ""
    Write-Log "================================================================================"
    Write-Log "MANUAL VALERO REPAIR COMPLETED SUCCESSFULLY"
    Write-Log "================================================================================"
    Write-Log "Success file: $SuccessFile"
    Write-Log "Backup folder: $BackupRoot"
    Write-Log "Tell Rohit: REPAIR COMPLETED SUCCESSFULLY."

    Copy-Item -Path $LogFile -Destination $LatestLogFile -Force

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "REPAIR COMPLETED SUCCESSFULLY" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Please tell Rohit: REPAIR COMPLETED SUCCESSFULLY"
    Write-Host ""
    Write-Host "Log file:"
    Write-Host $LogFile
    Write-Host ""
    Write-Host "Backup folder:"
    Write-Host $BackupRoot
    Write-Host ""

    Read-Host "Press ENTER to close this window"
    exit 0
}
catch {
    Complete-WithFailure "Unexpected error: $($_.Exception.Message)"
}