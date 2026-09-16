# Current architecture

This guide follows current source, audited on 2026-09-16. Paths below are repository-relative. There is no implemented database-backed run state, generic retry engine, server, or queue.

## Entry points

| Entry point | Responsibility |
| --- | --- |
| `scripts/run_daily_task.ps1` | Windows scheduled wrapper; default arguments are `--write-excel --write-originals --notify` for the batch runner |
| `scripts/run_daily_batch.py` | CITGO/SUNOCO requested date defaults to yesterday; VALERO defaults to today; one lock and combined notification |
| `scripts/daily_batch.py` | Near-duplicate batch implementation; not the script selected by the PowerShell wrapper |
| `scripts/run_daily.py` | One requested date, selected suppliers, full fetch-to-notification workflow, JSON artifact and exit status |
| `scripts/run_daily_parse_write_notify.py` | Local discovery → parse/validate → optional Excel/notification; materially weaker error gating than the full runner |
| `src/settlement_automation/cli.py` | Local parser/validation preview and optional CSV export; no fetch, Excel, or email |
| `scripts/write_excel_probe.py`, `scripts/write_excel_range.py` | Validate existing raw input before planning/resolving/applying Excel writes |

`scripts/_path_setup.py` adds the repository root and `src` to Python's import path. Top-level `config/` is a runtime dependency; packaging only discovers packages under `src`, so repository-root execution remains important.

## Scheduled execution sequence

1. The PowerShell wrapper resolves its own parent directory, changes working directory, checks the Windows venv and batch script, and tees child output to timestamped/latest logs.
2. `run_daily_batch.main` loads local environment configuration, resolves the two requested dates, and acquires `output/locks/daily_pipeline.lock` through `RunLock`.
3. It calls `run_daily_fetch_parse_write_notify` for `['citgo', 'sunoco']`, with notifications disabled inside that call.
4. It writes that result's JSON artifact, then calls the same service for `['valero']` and writes its artifact. The batch therefore uses separate DTN sessions for CITGO and VALERO. A single-date `run_daily.py --suppliers dtn` shares their login.
5. If `--notify` is set, `handle_daily_batch_notification` generates combined content, supplier PDFs, previews, and optionally sends one Graph email according to configuration.
6. The lock is released, results are printed, and the script returns 0 for no recorded errors, 1 for handled pipeline/send failures, or 2 for most uncaught exceptions. Non-lock `RuntimeError` is re-raised by a special handler rather than converted to 2.

Handled supplier errors normally do not prevent the second batch part from running. An uncaught exception, artifact-write failure, or lock failure can stop the batch. Per-run JSON is written **before** combined notification; no combined batch artifact records that send result.

## Inside the full daily service

`src/settlement_automation/services/daily_pipeline.py` performs:

```text
requested suppliers/date
  -> portal grouping (DTN first, SUNOCO second)
  -> fetch all requested groups and store raw files
  -> for every successful raw path: content dispatch -> parse -> validate
  -> for each report without parse/validation errors: optional Excel writer
  -> summary + anomalies
  -> optional single-run notification
  -> DailyPipelineResult returned to script
```

Fetching completes before the parse loop starts. A failed fetch is recorded and skipped. Successful fetches with no raw paths are errors. Parse exceptions become `RunError(stage='parse')`; validation ERROR issues become blocking report errors. Parsed reports with validation errors still appear in summary/PDF data, although the full service skips their Excel writes. Excel exceptions are caught per report; other reports continue.

`run_daily_parse_write_notify` instead searches local files by supplier/date substrings and newest modification time. It does **not** gate writes on validation errors, catch notification exceptions, acquire the daily lock, or persist JSON through its script. Do not assume the two services have identical safeguards.

## Subsystems and dependencies

| Source | Responsibility / consumers |
| --- | --- |
| `config/settings.py`, `supplier_accounts.py`, `portal_rules.py` | Runtime settings, credentials variable names, and portal routing |
| `connectors/browser.py`, `credentials.py`, `base.py`, `__init__.py` under `src/settlement_automation/` | Playwright Chromium session lifecycle, externally configured credentials, connector contract/factory |
| `connectors/dtn_*.py`, `ingestion/dtn_group_fetch.py` | DTN login, date/row selection, visible-text capture and shared-session fetch |
| `connectors/sunoco_*.py` | Login, capture frontend auth headers, paginated OData requests, validate/save JSON text |
| `connectors/download_manager.py`, `ingestion/fetch_reports.py` | Store raw reports and produce `StoredRawReport` / `FetchResult` |
| `services/report_processor.py`, `parser_registry.py`, `parsers/*_parser.py` | Content-based selection and supplier-specific extraction into `ParsedReport` |
| `models.py`, `utils/money.py`, `utils/dates.py`, `utils/text.py` | Dataclasses and shared numeric/date/detection helpers |
| `services/validation.py`, `reconciliation.py` | Invariants and adjustment aggregation; no external ledger reconciliation |
| `config/excel_mapping.py`, `config/locations.py`, `services/excel_writer.py` | Workbook identity, plan, cell resolution, and writes using openpyxl |
| `services/daily_run_summary.py`, `anomaly_detector.py`, `daily_run_artifacts.py` | Aggregate result/error/warning counts and JSON serialization |
| `services/notifications.py`, `daily_batch_notification.py` | Text/HTML construction, notification policy, previews and dispatch |
| `services/notification_pdfs.py`, `email_models.py`, `email_senders.py` | ReportLab PDFs and Graph HTML mail with in-memory PDF attachments |
| `services/audit_exporter.py` | Ten CSV outputs when explicitly requested by parser CLI; not part of the daily service |
| `services/console_output.py`, `diagnostics.py`, `run_lock.py` | Operator output, structured failure diagnostics, nonblocking OS file lock |

The subsystem paths in this table after `config/` are within `src/settlement_automation/`. Details: [DATA_FLOW](DATA_FLOW.md), [PARSER_GUIDE](PARSER_GUIDE.md), [EXCEL_WRITER](EXCEL_WRITER.md).

## Outputs, notifications, and observability

Notification bodies describe fetches, parsed data, Excel counts, warnings/anomalies, and errors. The single-run subject is `[OK|WARNING|ERROR] Credit Cards Daily Settlement Report - Report Date ...`; batch uses `Credit Cards Daily Settlement Batch - Run Date ...`. An enabled notification can describe failures and still be sent. There is no independent failure-alert channel.

`notification_pdfs.py::build_supplier_pdf_attachments` creates one PDF per parsed report under `output/notifications/{requested-report-date}_{supplier}_summary.pdf`. ReportLab builds portrait Letter tables directly from dataclasses, with daily rows, applicable supplier summaries, adjustments and unclassified rows. No external PDF template or Excel-to-PDF conversion is used. PDFs are generated only in notification preview/send processing; repeated supplier/date names overwrite.

Single-run previews use `{report-date}_daily_summary.txt/.html`; combined previews use `{task-date}_daily_batch_summary.txt/.html`. Single-run handling writes preview before PDFs; batch handling builds PDFs before preview. Exceptions propagate to the surrounding runner/service; PDF failure is not an independently retried stage. Attachments are these generated PDFs, not raw reports, CSVs, or workbooks.

Microsoft Graph uses client credentials and standard-library HTTP requests, with 30-second request timeouts. `sent=True` means the HTTP send call succeeded, not proof of mailbox delivery. No send retry or deduplication is implemented. `smtp` is accepted as configuration but sending returns an unimplemented error. See [CONFIGURATION](CONFIGURATION.md).

Console prints and wrapper tee logs are the main logs. `utils/logging_utils.py` is empty. Diagnostics contain exception messages/tracebacks and optional browser artifacts; traces can contain sensitive session data and must be treated accordingly.

## Placeholder and auxiliary files

`ingestion/pipeline.py`, `process_reports.py`, `retry_policy.py`, `state_store.py`, and `parsers/base.py` are empty, not active layers. `services/report_detector.py` is a thin registry-based supplier detector. `data/incoming/`, `data/processed/`, `data/failed/`, and `data/backups/` exist as scaffolding; daily fetch does not archive reports through a processed/failed state machine. Old `data/raw/dtn/.../DD` folders do not define the current storage contract.

Separate creation/clearing and dated repair scripts affect workbooks but are not automatically invoked by daily processing. There are no tracked workbook/PDF templates, CI workflow, Task Scheduler XML/setup, or cron registration. Installed production scheduling and external workbook layout remain **Needs verification**.
