# Operations runbook

Commands below use current parser definitions and entry points; all documented primary Python entry points were checked with `--help` during the audit. PowerShell commands were source-reviewed, not executed on a Windows production host. Live fetches, original workbook writes, scheduled tasks and actual email delivery are **Needs verification**.

## Start from a fresh PowerShell window

Run the following first. Enter the actual checkout path when prompted; this avoids assuming a machine-specific location.

```powershell
$repo = Read-Host 'Full path to the repository checkout'
Set-Location -LiteralPath $repo
$python = Join-Path $repo '.venv\Scripts\python.exe'
$env:PYTHONPATH = (Join-Path $repo 'src')
Test-Path $python
& $python --version
```

Use the venv interpreter directly; activation is optional. If desired, `& .\.venv\Scripts\Activate.ps1` activates an existing Windows environment. Do not reuse a macOS/Linux venv on Windows.

For a new environment, the repository dependency files imply this setup (not executed during the documentation audit):

```powershell
py -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
& .\.venv\Scripts\python.exe -m playwright install chromium
```

Python must satisfy `pyproject.toml`'s >=3.10 declaration and the installed requirement pins; exact fresh-install compatibility is **Needs verification**. Configure supplier credentials, workbook roots and notifications externally; see [CONFIGURATION](CONFIGURATION.md). No application dependency was added in this audit.

## Scheduled production invocation

The repository's scheduled wrapper is:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_daily_task.ps1
$LASTEXITCODE
```

**This requests original workbook writes and notification.** It runs `.venv\Scripts\python.exe scripts\run_daily_batch.py --write-excel --write-originals --notify`. Notification configuration decides whether it actually sends. The wrapper changes to its own repository root, so an installed task can use its absolute script path.

No Task Scheduler registration/XML, trigger schedule, task user, or retry configuration is tracked. Verify the installed task separately, especially its access to external workbook folders. Historical `C:\CC Automation\settlement-automation` and `P:\AUTOMATED_CC_WORKBOOKS` appear in repair scripts only.

Wrapper switches:

| Switch | Effect |
| --- | --- |
| `-ExcelDryRun` | Resolve plans without workbook writes; still fetches and requests notification unless `-NoNotify` |
| `-NoWriteExcel` | Omit `--write-excel`; fetching/parsing and optional notification still occur |
| `-NoWriteOriginals` | Use output copies when writing, rather than originals |
| `-NoNotify` | Omit notification, including its preview/PDF generation |

A fetch/parse/Excel-resolution check without email or workbook writes is:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_daily_task.ps1 -ExcelDryRun -NoNotify
```

This still logs into suppliers and replaces same-date raw files. It is **not** an offline test.

## Daily and selected-date commands

The batch executes CITGO then SUNOCO in its first service call, followed by VALERO in the second. Defaults: CITGO/SUNOCO requested report date yesterday, VALERO today. It holds one process lock, writes two per-run JSON artifacts and optionally sends one combined email.

Python batch equivalent of the scheduled production action:

```powershell
& $python .\scripts\run_daily_batch.py --write-excel --write-originals --notify
```

Explicit dates, workbook preview, no notification:

```powershell
& $python .\scripts\run_daily_batch.py --citgo-sunoco-report-date 2026-07-06 --valero-report-date 2026-07-07 --write-excel --excel-dry-run
```

Single-date full fetch/parse runner examples (no workbook writes or notification unless enabled):

```powershell
& $python .\scripts\run_daily.py --suppliers valero --report-date 2026-07-10
& $python .\scripts\run_daily.py --suppliers citgo,valero --report-date 2026-07-10
& $python .\scripts\run_daily.py --suppliers all --days-back 1
```

For SUNOCO, report/settlement date July 6 produces July 5 transaction rows; do not add a day because of the legacy fetch parameter name. For VALERO, inspect all output transaction dates, including weekend and late-date blocks. Requested supplier/date is not cross-checked against detected supplier/header date.

| Runner | Complete task-specific flags (all also have `--help`) |
| --- | --- |
| `run_daily.py` | `--report-date`, `--days-back` (default 1, nonnegative if no explicit date), `--suppliers` (`all`, `dtn`, individual/comma-separated), `--write-excel`, `--excel-dry-run`, `--write-originals`, `--notify` |
| `run_daily_batch.py` / `daily_batch.py` | `--citgo-sunoco-report-date`, `--citgo-sunoco-days-back` (1), `--valero-report-date`, `--valero-days-back` (0), `--write-excel`, `--excel-dry-run`, `--write-originals`, `--notify`; no supplier flag |
| `run_daily_parse_write_notify.py` | `--report-date`, declared `--business-date` alias, space-separated required `--suppliers`, `--write-excel`, `--excel-dry-run`, `--write-originals`, `--notify` |

The local parse/write/notify script requires `--report-date` in practice: the advertised `--business-date` alias is unused and omission fails in `date.fromisoformat`. Its local finder chooses newest mtime among `.txt/.csv/.json` paths containing supplier and ISO-date text under raw/incoming/tmp/processed. It has no lock/artifact, does not gate Excel on validation errors, does not load `.env`, and does not convert summary failures into exit 1. Prefer the validating file/range tools below for workbook replay.

## Local inspection and historical replay

Point explicitly at a retained raw file; these examples require that file to exist. They do not fetch from a portal.

```powershell
& $python .\scripts\parse_raw_probe.py --file .\data\raw\valero\2026\07\valero_2026-07-10.txt
& $python -m settlement_automation.cli --file .\data\raw\valero\2026\07\valero_2026-07-10.txt --preview
& $python -m settlement_automation.cli --file .\data\raw\valero\2026\07\valero_2026-07-10.txt --export-csv --output-dir .\output\reports
```

Module CLI options are `--file` (required), `--preview` (compatibility flag; output already prints), `--export-csv`, `--output-dir` (default `output/reports`). It returns 1 for missing input or invalid validation; parse exceptions are not handled. CSV export is independent of daily JSON/PDF output and can run even when validation is invalid.

Workbook dry-run against an **isolated folder of copied workbooks**:

```powershell
$workbooks = Read-Host 'Full path to isolated workbook copies'
$previewOutput = Join-Path $env:TEMP 'prestige-excel-preview'
& $python .\scripts\write_excel_probe.py --file .\data\raw\valero\2026\07\valero_2026-07-10.txt --workbook-root $workbooks --output-root $previewOutput
```

Add `--write` to save output copies; add `--write-originals` only for an authorized change to files in the supplied root. `--no-backup-originals` disables original backups and is not a routine recovery option. `write_excel_probe` rejects originals without `--write`, blocks invalid reports, and otherwise returns 0 even with writer warnings.

Inclusive historical local range (default dry-run):

```powershell
& $python .\scripts\write_excel_range.py --supplier valero --start-date 2026-07-01 --end-date 2026-07-10 --raw-root .\data\raw --workbook-root $workbooks --output-root $previewOutput --skip-missing --continue-on-error
```

Range flags: `--supplier` (`valero` default, `citgo`, `sunoco`), required `--start-date`/`--end-date`, `--raw-root` (`data/raw`), `--workbook-root`, `--output-root`, `--write`, `--write-originals`, `--no-backup-originals`, `--continue-on-error`, `--skip-missing`. It expects exactly `{raw-root}/{supplier}/YYYY/MM/{supplier}_{date}.txt`, iterates dates ascending and does not discover older directory conventions or JSON suffixes. Default stops on failure; skipped missing files are counted separately when requested. Exit 1 means a date failed; warnings alone need not fail.

Re-fetching history with `run_daily.py --report-date` replaces raw files. Raw retention is not versioned. Copy-mode Excel starts from source workbooks each call and replaces same-report-date output copies; a range is not one cumulative output workbook. Original-mode historical changes require review of SET/additive rules, marker columns, hidden operation log and partial-save risk in [EXCEL_WRITER](EXCEL_WRITER.md).

## Fetch and portal troubleshooting tools

```powershell
& $python .\scripts\fetch_only.py --supplier citgo --business-date 2026-07-06
& $python .\scripts\fetch_and_parse_probe.py --suppliers dtn --business-date 2026-07-06
& $python .\scripts\probe_dtn_range_download.py --start-date 2026-07-01 --end-date 2026-07-10 --suppliers citgo,valero
```

These are live fetch commands and overwrite same-date raw files. The old `--business-date` name supplies the requested report date under the current connectors.

- `fetch_only.py`: required `--supplier`; `--business-date` defaults yesterday; `--mock-source-file` uses a local fake download; `--remove-source` moves that mock input instead of copying. Mock mode still writes the configured repository raw storage, so do not use a production supplier/date accidentally.
- `fetch_and_parse_probe.py`: select exactly one of `--supplier` or `--suppliers`; `--business-date` defaults yesterday. Fetch/parse/validation failures produce diagnostics; no Excel or email. Returns 1 when any selected result fails.
- `probe_dtn_range_download.py`: required start/end, `--suppliers` defaults both DTN suppliers; `both`, `dtn`, `all` all mean CITGO/VALERO here. Optional `--skip-weekends`, `--record-trace`. Reuses one login over the range. `NOT_FOUND` and skipped weekends do not cause exit 1; unexpected failures do.
- Live UI probes are under `scripts/probes/`: `probe_dtn_dataconnect.py`, `probe_dtn_click_capture.py`, `probe_sunoco_login.py`, `probe_sunoco_api.py`. Inspect their flags and bootstrap before use; old README paths omit this subdirectory. These can capture sensitive page/session data. No live probe was run for this audit.

## Notification preview without sending

This existing helper does **not** load `.env`, so explicit shell mode applies to this command. It parses a local file and generates text/HTML/PDF output without workbook writes:

```powershell
$env:NOTIFICATION_EMAIL_ENABLED = 'true'
$env:NOTIFICATION_EMAIL_MODE = 'dry_run'
$env:NOTIFICATION_EMAIL_PROVIDER = 'graph'
& $python .\scripts\send_test_notification_email.py --file .\data\raw\valero\2026\07\valero_2026-07-10.txt --business-date 2026-07-10 --supplier valero
```

The helper requires `--business-date`; `--file` is optional, otherwise it searches by supplier/date and newest mtime. `--supplier` defaults valero. It does not validate reports or enforce `test` mode and may return process success despite an error in its printed notification result. `test`/`live` modes really send. Full runners that load `.env` can override these shell values; use `--notify` only with verified effective configuration. Preview helper output is under `output/notifications/` and can overwrite same-date previews/PDFs.

## Checking status

```powershell
Get-Content .\output\logs\daily_task_latest.log -Tail 100
$run = Get-Content .\output\daily_runs\latest.json -Raw | ConvertFrom-Json
$run | Select-Object report_date, run_date, started_at, finished_at, status
$run.counts
$run.fetch_results
$run.errors
$run.warnings
$run.excel_results
```

For the scheduled batch, also inspect both printed artifact paths under `output/daily_runs/{requested-date}/`. `latest.json` normally contains the second (VALERO) run only; it is not a batch-wide result. Both batch artifacts precede combined email and have no combined notification result. The wrapper log/exit code is necessary for that final stage. Check timestamps before treating an old `latest` file as the latest attempted run.

Normal daily exit meanings: **0** no recorded errors (warnings allowed), **1** handled pipeline/send failure or lock contention, **2** most unexpected failures / wrapper preflight failures. Invalid argparse usage also returns 2. Non-lock `RuntimeError` is re-raised, so these codes are not an exhaustive taxonomy. A crash before artifact writing can leave the old `latest.json` unchanged.

JSON status is `error` if summary or single-run send has an error, `warning` for warnings/anomalies, otherwise `success`. Counts are not completeness checks: supplier names include only parsed reports; Excel writes count cells; unresolved targets may warn without increasing skipped counts. An empty/no-write run can have no errors. Inspect warnings, intended dates/locations, and actual output before declaring financial completion.

## Failure recovery

| Symptom | Start here and recover within the intended scope |
| --- | --- |
| Fetch failure | Check `fetch_results`/fetch-stage errors, credential variable presence without printing values, portal date availability, `output/diagnostics/{supplier}/{date}` and protected traces. Full flow does not fall back to an old local raw file after fetch failure. Preserve raw evidence before authorized refetch |
| Parse failure | Run parser CLI on the exact raw path; it exposes the underlying exception that daily summary may reduce to type/path. Check dispatch/header markers, capture completeness, JSON shape, date formats and adjustment section boundaries |
| Unexpected totals | Compare raw details/SUB rows to parsed rows and CSVs; inspect sign/date semantics, duplicate input, VALERO classification, SUNOCO recomputed net and separate discounts; compare notification totals separately from workbook totals |
| Validation failure | Review empty/duplicate daily rows and gross-fee-net checks. Full pipeline skips Excel for that report. Do not bypass by using the weaker local service |
| Excel lock/permission error | Close external editors and competing jobs, verify access to source/output/backup folder. Read warnings and traceback-producing probe on copies. Earlier workbooks can have been saved; do not assume rollback or blindly replay |
| Missing/wrong workbook, sheet, header or date row | Review expected filename, normalized/fuzzy match warning, office mapping, month aliases, first 10 header rows and date-anchor inference. Dry-run resolves actual cells before authorized write |
| Marker mismatch / skipped formula | Review existing gross/net formulas, mobile/Pay+ marker and operation log against source report. Do not erase protections solely to force an addition |
| PDF failure | Check ReportLab import, notification directory permissions and local report data; failure can prevent send. Single-run full service records notification-stage error; batch may terminate after its JSON artifacts already exist |
| Email failure | Check enabled/mode/provider, `NotificationResult.error_message`, required Graph variable names, effective recipient list and HTTP response. SMTP send is unimplemented. Graph success does not prove delivery; resend can duplicate mail |
| Another run already active | Identify the process holding the OS lock and wait for it. The persisted lock file itself is not evidence of an active run; deleting it is not the normal unlock mechanism |

There is no automatic whole-run retry, checkpoint resume, or rollback. Recommendations here are operational inspection steps, not implemented recovery automation.

## Creation, clearing, and dated repair scripts

`create_settlement_workbooks.py` accepts required `--year`, optional `--output-dir` (default `data/excel/settlements`), `--supplier`, `--location-id`, `--location-name`, `--overwrite`, `--dry-run`. It creates workbooks by default, skips existing files unless overwrite is requested, and has naming/header mismatches with the writer documented in [KNOWN_ISSUES](KNOWN_ISSUES.md). It is not part of daily processing.

`clear_excel_entries.py` accepts required `--workbook-root`, optional `--output-root`, either `--month` or start/end dates, `--write`, `--write-originals`, `--no-backup-originals`, and `--preserve-formula-columns` (default `CC Fee,DIFF`). It scans all immediate `.xlsx` workbooks, not a supplier filter, clearing matching-date non-Date cells except formulas under preserved headers. This includes manual data and other formulas; it does not clear the hidden automation operation log. Default is dry-run. Do not run it as generic retry recovery.

`repair_valero_2026_07_10.ps1` is a one-time July repair: stage/back up VALERO workbooks, clear July 8–9, copy back to the shared root, then refetch/write July 9 and July 10 (last requests notification). `repair_script.cmd` can stash changes, fetch Git and hard-reset before launching it. `RUN_MANUAL_SETTLEMENT_FIX.txt` contains historical batch commands for original writes. These are historical high-impact tools, not current routine run instructions, and were not executed during the audit.
