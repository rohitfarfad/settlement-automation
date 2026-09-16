# Working on Prestige settlement automation

This is production financial automation for Prestige Petroleum credit-card settlements from CITGO, VALERO, and SUNOCO. Preserve financial meaning and existing production behavior unless the task explicitly changes it.

## Prefer minimal code and simple implementations

- Use the smallest correct implementation and the fewest necessary file/line changes. A bug fix should fix the bug, not redesign the subsystem.
- Search for existing implementations and helpers first; follow established patterns. Add abstractions only when they clearly reduce complexity.
- Avoid speculative classes, layers, services, wrappers, helper modules, frameworks, design patterns, configuration, and extension points. Supplier-specific logic can be clearer than forcing incompatible formats into a generic abstraction.
- Do not perform unrelated cleanup, formatting, renaming, or directory reorganization. Report unrelated problems separately.
- Use the standard library and existing dependencies where practical; justify any new dependency concretely.
- Prefer explicit, understandable logic over clever expressions. Prioritize correctness, traceability, understandable logic, regression safety, and simplicity over architectural elegance.

## Sources of truth

`README.md` is deprecated/outdated. `README_updated.md` also contains obsolete behavior. Neither is an operating manual.

Use this order: current source → current scripts/entry points → tests/fixtures → configuration → models/schemas → sample inputs/outputs → operational scripts → safe tracked run artifacts → documentation → README as historical background. Tests can be stale: the audit baseline is **68 passed, 10 failed**; see [TESTING](docs/TESTING.md). Mark unsupported facts **Needs verification**. Never infer an implemented feature from an empty module or an old comment.

## Architecture and navigation

- Scheduled wrapper: `scripts/run_daily_task.ps1` → `scripts/run_daily_batch.py`. Default wrapper writes original workbooks and requests notification. CITGO/SUNOCO use yesterday's report date; VALERO uses today's.
- Single-date full runner: `scripts/run_daily.py`; orchestration: `src/settlement_automation/services/daily_pipeline.py::run_daily_fetch_parse_write_notify`.
- `src/settlement_automation/connectors/` logs into DTN/Sunoco and captures raw data; `ingestion/` groups suppliers and stores files.
- Parsing: `services/report_processor.py::parse_report` → `services/parser_registry.py` → `parsers/*_parser.py` → dataclasses in `models.py`.
- `services/validation.py`, `reconciliation.py`, `excel_writer.py`, `daily_run_summary.py`, `notifications.py`, `notification_pdfs.py`, and `email_senders.py` handle downstream processing.
- `config/` contains settings, portal rules, location identities, and workbook mapping. `data/raw/` holds fetched reports; `output/` holds run JSON, notifications, diagnostics, traces, and workbook copies/backups. `scripts/probes/` contains live portal diagnostics.

## Development and verification

1. Trace the affected entry point through its consumers before editing. Read the relevant guide below and inspect the actual source.
2. Keep work scoped. Explain before/after financial behavior for changes to amounts, classifications, dates, formulas, or destinations.
3. Use representative, sanitized fixtures, temp directories, mocks, and existing dry-run mechanisms. Inspect existing tests before running them; never substitute a live portal probe for a unit test.
4. Run relevant tests and compare with the documented baseline. Do not change unrelated behavior simply to make a stale assertion pass. Update documentation when actual behavior changes.
5. Verify CLI options against parser definitions/`--help`; check `git diff --check` and the final diff for unintended changes.

From the repository root in PowerShell, with an existing environment:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
$env:PYTHONDONTWRITEBYTECODE = '1'
& .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

On macOS/Linux: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -q -p no:cacheprovider`. Setup and limitations: [CONFIGURATION](docs/CONFIGURATION.md), [TESTING](docs/TESTING.md).

## Production safety and parser changes

- Do not silently discard records, change amount signs/date semantics/supplier classification, redirect Excel destinations, or change formulas.
- For parser changes, inspect representative raw inputs, dispatch markers, normalized fields, validation, reconciliation, Excel plans, and notification totals. Cover relevant boundaries (year/month/weekend, late dates, duplicates, unknown rows). Parsers reread the original file after normalized-text detection.
- Never send production email during tests unless explicitly requested. `test` mode really sends to the test recipient; `--excel-dry-run` does **not** disable fetching or email. `send_test_notification_email.py` does not force test mode.
- Never overwrite production Excel files while experimenting. Use explicit isolated workbook/output roots; `--write-originals` changes source workbooks. Copy mode overwrites same-date output copies. Warnings do not necessarily block writing.
- Raw fetch reruns overwrite the supplier/date file. Preserve an input separately before investigating a changed portal report.
- Do not read, print, or commit secrets, auth headers, cookies, tokens, private recipient addresses, or sensitive browser traces. `.env` loading uses `override=True` and can override shell settings.
- Daily runners use a process lock; probes and repair tools do not all share it. Do not run them concurrently against production workbooks. Historical repair wrappers clear data and can reset Git; they are not routine run commands.

## Detailed operating manual

[Project context](docs/PROJECT_CONTEXT.md) · [Architecture](docs/ARCHITECTURE.md) · [Data flow](docs/DATA_FLOW.md) · [Parser guide](docs/PARSER_GUIDE.md) · [Supplier integrations](docs/SUPPLIER_INTEGRATIONS.md) · [Excel writer](docs/EXCEL_WRITER.md) · [Operations runbook](docs/OPERATIONS_RUNBOOK.md) · [Configuration](docs/CONFIGURATION.md) · [Testing](docs/TESTING.md) · [Known issues](docs/KNOWN_ISSUES.md) · [Decisions](docs/DECISIONS.md)
