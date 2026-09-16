# Project context

## Business purpose and boundaries

The project automates Prestige Petroleum's supplier credit-card settlement reporting: collect supplier reports, interpret settlement amounts by location/date, update location Excel workbooks, and produce operator summaries and email attachments. This purpose is supported by the supplier accounts, settlement models, workbook mappings, and notification content in the repository.

The implemented suppliers are **CITGO, VALERO, and SUNOCO**. CITGO and VALERO share DTN Fuel Buyer/DataConnect; SUNOCO uses its own portal and authenticated settlement API. No other supplier implementation is registered.

Business ownership, reconciliation sign-off, banking/draft timing, holiday calendars, and report retention requirements are **Needs verification**. The code does not establish these policies. It does not initiate bank payments or implement a general ledger integration.

## Current application scope

The application is a Python package plus operator scripts, not a running web service. Its main workflows are:

| Workflow | Current implementation |
| --- | --- |
| Scheduled daily processing | PowerShell wrapper runs a two-part Python batch, writes Excel originals by default, and requests one combined notification |
| One report date / selected suppliers | `scripts/run_daily.py` fetches, parses, validates, optionally writes Excel and notifies |
| Inspect an existing input | `scripts/parse_raw_probe.py` or `python -m settlement_automation.cli` |
| Local workbook replay | `scripts/write_excel_probe.py` or inclusive-date `scripts/write_excel_range.py` |
| Fetch only / portal troubleshooting | `scripts/fetch_only.py`, `scripts/fetch_and_parse_probe.py`, DTN range and `scripts/probes/` tools |
| Workbook preparation / repair | Separate workbook creation, clearing, and dated repair scripts; these are outside the routine daily pipeline |

The fetch workflow stores raw files before parsing. Parser dataclasses are the normalized data; there is no separate generic normalization engine. Excel workbooks remain operational output, with supplier-specific treatment of fees and adjustments. PDF summaries are generated from parsed reports during notification processing, not by converting Excel files.

## Operator environment

Windows/PowerShell is an explicit operational target: `scripts/run_daily_task.ps1` locates `.venv\Scripts\python.exe`, changes to the repository root, captures console output, and returns the child exit code. Python processing and the run lock also support non-Windows environments. The documentation audit ran offline tests on macOS with Python 3.12; that does not verify Windows portal access or production workbook behavior.

No tracked Task Scheduler registration/export specifies the task account, trigger, time zone, or schedule. The wrapper is the repository's intended scheduled entry point; the actual installed task is **Needs verification**.

Historical repair files reference `C:\CC Automation\settlement-automation` and `P:\AUTOMATED_CC_WORKBOOKS`. These are machine-specific repair paths, not portable defaults or proof of current production configuration.

## Terminology that affects correctness

| Term | Meaning in current code |
| --- | --- |
| Run/task date | Host-local `date.today()` when executing; used for batch labels and anomaly rules |
| Requested report date | Date selected by the caller and used to fetch/store a report |
| Parsed report date | Date read from supplier content; may differ from the caller's date and is not checked against it |
| Business/transaction date | Date on a normalized row, used to select workbook year, month sheet, and date row |
| `business_date` in fetch APIs | Legacy parameter name; the daily pipeline passes its requested **report** date |
| Daily total | Gross, fees, and net for one supplier/location/date |
| Mobile adjustment | VALERO detail from a location/date not classified as daily; not restricted to mobile card codes |
| Pay+ | VALERO `VP+ Fuel Offer` adjustment; dealer and wholesaler workbook handling differs |
| Monthly charge | VALERO adjustment normalized to a positive fee and assigned to the latest expected settlement date |
| Unclassified adjustment | Recognized VALERO adjustment-section row retained for warning/review; not written to Excel |
| SUNOCO discount | JSON `adjustments`, stored and reported separately from recomputed daily net |

## Constraints for future work

Financial correctness, traceability, minimal changes, and understandable supplier-specific logic take priority. The test suite has a known failing baseline and sparse parser/Excel coverage. No tracked real workbook templates or populated sample report files are available to prove full production compatibility. Workbook warnings can represent skipped output while the process still exits successfully. See [KNOWN_ISSUES](KNOWN_ISSUES.md) and [OPERATIONS_RUNBOOK](OPERATIONS_RUNBOOK.md).

Evidence: `config/supplier_accounts.py`, `config/locations.py`, `src/settlement_automation/models.py`, `src/settlement_automation/services/daily_pipeline.py`, and the runner scripts. Old READMEs are historical context only.
