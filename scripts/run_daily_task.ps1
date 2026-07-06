[CmdletBinding()]
param(
    [string]$Suppliers = "all",
    [int]$DaysBack = 1,
    [switch]$ExcelDryRun,
    [switch]$NoWriteExcel,
    [switch]$NoWriteOriginals,
    [switch]$NoNotify
)

$ErrorActionPreference = "Stop"

try {
    $ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
    Set-Location $ProjectRoot

    $LogDir = Join-Path $ProjectRoot "output\logs"
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

    $RunTimestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $LogFile = Join-Path $LogDir "daily_task_$RunTimestamp.log"
    $LatestLogFile = Join-Path $LogDir "daily_task_latest.log"

    function Write-Log {
        param([string]$Message)

        $Line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
        $Line | Tee-Object -FilePath $LogFile -Append
    }

    $PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    $RunDailyPy = Join-Path $ProjectRoot "scripts\run_daily.py"

    Write-Log "WINDOWS DAILY TASK WRAPPER"
    Write-Log "================================================================================"
    Write-Log "Project root   : $ProjectRoot"
    Write-Log "Python         : $PythonExe"
    Write-Log "Run script     : $RunDailyPy"
    Write-Log "Suppliers      : $Suppliers"
    Write-Log "Days back      : $DaysBack"
    Write-Log "Excel dry run  : $ExcelDryRun"
    Write-Log "No write Excel : $NoWriteExcel"
    Write-Log "No originals   : $NoWriteOriginals"
    Write-Log "No notify      : $NoNotify"
    Write-Log ""

    if (-not (Test-Path $PythonExe)) {
        Write-Log "ERROR: Python executable not found at $PythonExe"
        exit 2
    }

    if (-not (Test-Path $RunDailyPy)) {
        Write-Log "ERROR: run_daily.py not found at $RunDailyPy"
        exit 2
    }

    $Arguments = @(
        $RunDailyPy,
        "--suppliers", $Suppliers,
        "--days-back", "$DaysBack"
    )

    if (-not $NoWriteExcel) {
        $Arguments += "--write-excel"
    }

    if ($ExcelDryRun) {
        $Arguments += "--excel-dry-run"
    }
    elseif (-not $NoWriteOriginals) {
        $Arguments += "--write-originals"
    }

    if (-not $NoNotify) {
        $Arguments += "--notify"
    }

    Write-Log "Starting daily pipeline..."
    Write-Log "Command        : $PythonExe $($Arguments -join ' ')"
    Write-Log ""

    & $PythonExe @Arguments *>&1 | Tee-Object -FilePath $LogFile -Append

    $ExitCode = $LASTEXITCODE

    Write-Log ""
    Write-Log "Finished at    : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    Write-Log "Exit code      : $ExitCode"

    Copy-Item -Path $LogFile -Destination $LatestLogFile -Force

    exit $ExitCode
}
catch {
    $Message = $_.Exception.Message

    try {
        if ($LogFile) {
            "FATAL WRAPPER ERROR: $Message" | Tee-Object -FilePath $LogFile -Append
            Copy-Item -Path $LogFile -Destination $LatestLogFile -Force -ErrorAction SilentlyContinue
        }
        else {
            Write-Host "FATAL WRAPPER ERROR: $Message"
        }
    }
    catch {
        Write-Host "FATAL WRAPPER ERROR: $Message"
    }

    exit 2
}