# Testing and audit baseline

The repository uses pytest with inline synthetic data, fake connectors/request clients, `tmp_path`, and `monkeypatch`. There is no pytest configuration or tracked CI workflow. `pyproject.toml` declares Python >=3.10 and package discovery under `src`; `requirements.txt` lists pytest and runtime packages. No tests were added or modified for this documentation phase.

## Run the existing suite

From the repository root in a fresh PowerShell window with an existing Windows venv:

```powershell
$repo = Read-Host 'Full path to repository checkout'
Set-Location -LiteralPath $repo
$env:PYTHONPATH = (Join-Path $repo 'src')
$env:PYTHONDONTWRITEBYTECODE = '1'
& .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Equivalent on macOS/Linux:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -q -p no:cacheprovider
```

The suite does not load root `.env`, log into suppliers, modify production workbooks or perform a successful external send in its existing cases. Notification tests supply explicit configs that are disabled/dry-run or fail send preconditions; fetch tests use fakes. PDF construction is exercised indirectly in a dry-run notification test with a temp directory. Maintain those isolation properties in future changes.

## Observed baseline on 2026-09-16

Executed with the existing macOS Python **3.12.6** venv:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -q -p no:cacheprovider --basetemp=/tmp/prestige-doc-audit-tests
10 failed, 68 passed in 0.65s
```

Exit code was 1. No dependency installation, live portal/email/production workbook action, code change or test change was performed. This is a baseline, not a green-suite claim.

| Failed tests | Actual mismatch |
| --- | --- |
| `tests/test_download_manager.py`: `test_store_sunoco_raw_report`, `test_store_citgo_dtn_raw_report`, `test_store_valero_dtn_raw_report` | Assertions expect old portal/day paths and portal-prefixed filenames; source stores supplier/year/month and deterministic supplier/date filenames |
| `tests/test_fetch_reports.py::test_fetch_reports_for_account_stores_downloaded_file` | Same old DTN raw layout assumption |
| `tests/test_notifications.py::test_build_daily_email_success_subject`, `test_handle_daily_notification_dry_run_writes_preview` | Expected old Prestige/Business Date subject; current text uses Credit Cards/Report Date |
| Both tests in `tests/test_sunoco_date.py` | Expect +1 day; active helper returns supplied report date unchanged |
| `tests/test_valero_parser.py::test_valero_unknown_adjustment_is_captured`, `test_valero_monthly_charge_is_not_unclassified` | Synthetic inputs omit ADJUSTMENTS section required by current parser for these categories |

These disagreements are confirmed. Whether a given test or implementation should change is a separate behavior decision; do not silently revert source to match old assertions.

## Test inventory and what it establishes

| Files in `tests/` | Existing coverage |
| --- | --- |
| `test_settings.py` | Browser/retry/timeout defaults and environment overrides; not full effective-config precedence |
| `test_credentials.py` | Supplier credential names, missing-value errors, password omitted from credential repr |
| `test_connector_factory.py` | Three active suppliers, portal connector types, unsupported supplier |
| `test_supplier_selection.py` | Single/multiple/dtn/all selection, deduplication, portal grouping |
| `test_dtn_reports.py`, `test_dtn_content_selection.py`, `test_dtn_date.py` | Target definitions, CITGO required/rejected markers, VALERO unrestricted fetch marker, padded dates |
| `test_sunoco_reports.py`, `test_sunoco_date.py` | Target metadata and legacy date expectations; date expectations fail |
| `test_sunoco_api.py` | OData filter/URL, endpoint recognition, transport-header filtering/auth retention, two-page fake response aggregation |
| `test_sunoco_capture.py` | Valid JSON marker check, invalid JSON/missing-marker rejection, temporary text-file save |
| `test_download_manager.py` | Copy/move/hash/path/source behavior, repeated same-file destination, missing file; old path tests fail |
| `test_fetch_reports.py` | Fake connector storage, move, error result and supplier failure isolation; not browser login |
| `test_valero_parser.py` | Four synthetic adjustment cases; VISA Pay+ and mixed mobile/daily/section classification pass, two sectionless cases fail |
| `test_excel_mapping.py` | Header text normalization and month sheet aliases only |
| `test_daily_run_summary.py` | Empty/count/error summary and retained-unclassified anomaly integration |
| `test_notifications.py` | Status subject/content, amount formatting, anomaly/error text, dry-run/disabled and missing-Graph handling |
| `test_email_senders.py` | Recipient delimiter handling, missing Graph config and missing To rejection; no successful HTTP send |

`tests/test_citgo_parser.py`, `tests/test_reconciliation.py`, and `tests/test_anomaly_detector.py` are zero-byte files. The latter subsystem has limited indirect coverage through summaries/notifications, not a populated direct suite.

Both `tests/sample_reports/citgo_sample.txt` and `valero_sample.txt` are zero bytes. There is no dedicated SUNOCO parser test file, populated sample-report directory, workbook fixture, PDF fixture, or test for dispatcher ambiguity/normalization. Do not cite these empty files as regression evidence.

## Major coverage gaps

- **Parser financial correctness:** CITGO extraction/sign/year rollover and duplicate raw rows; SUNOCO date/fee/discount/null/duplicate normalization; VALERO weekend/year rollover, late full-day heuristic thresholds, monthly assignment, malformed lines and successful section monthly/unclassified extraction.
- **Validation/reconciliation:** no dedicated tests for all net/duplicate/unknown-name checks or aggregation keys; no input-to-control-total completeness checks.
- **Excel:** no workbook plan/resolution/apply integration tests, formula/date-anchor/fuzzy-target tests, dealer/wholesaler Pay+, mobile/monthly rerun tests, backup/overwrite/permission/partial-save tests, or generator-writer compatibility tests. Mapping helper tests do not establish safe workbook updates.
- **Orchestration:** no daily/batch service tests for validation gating, grouped DTN failure isolation, two-date scheduling, artifact freshness, exit codes, lock contention or the weaker local service behavior.
- **Notifications/PDF:** no successful Graph HTTP mock/payload/attachment test, batch notification test, PDF content/layout assertion, or PDF/send failure recovery test. The existing dry-run notification case reaches PDF generation but fails its old text assertion.
- **Live integration:** no automated portal browser, production workbook/share, Windows Task Scheduler or actual mailbox-delivery verification.

`scripts/probes/` and other operator probes are manual tools, not automated integration tests. Most contact real portals; `fetch_only.py --mock-source-file` avoids a portal but still writes raw storage. Use explicit isolated paths/config objects for further testing.

## Verification performed for the documentation

The full existing suite was run once. The 13 primary scripts listed in the runbook and `python -m settlement_automation.cli` returned exit 0 for `--help`, confirming their option definitions/importability in the existing environment. This does not establish successful live execution or Windows shell availability. Documentation was cross-checked against source, path references, CLI definitions and the final Markdown-only diff.

For future code changes, run the smallest relevant tests and add meaningful isolated regressions for changed behavior as authorized. Compare failures with this baseline; preserve financial behavior outside the task. Do not “fix” unrelated tests during a scoped change.

## Sunoco adjustment fix verification (2026-09-28)

Per the user's instruction, the deprecated suite was not used as acceptance evidence. An isolated replay exercised the current application services against saved raw reports:

- 86 reports parsed and validated: 33 CITGO and 29 VALERO outputs were identical to the before-change baseline. Across 24 SUNOCO reports, 285 daily rows were unchanged and four changed by exactly `adjustments - totalFiveCentRollback`; fees and dates were preserved.
- The full daily service replayed downloaded files through normal raw storage, dispatch, validation, Excel planning/resolution/apply, notification previews/PDFs and run-artifact generation. The July 20 three-supplier run wrote 107 cells to temporary copies; reopening the output files confirmed every written value. Missing workbook/name mappings produced existing warnings, so this does not establish complete production workbook coverage.
- Central Ave's August attachment was reconstructed into a JSON fixture because the original August API response is unavailable. The flow wrote gross 9,814.75 and net 9,615.89, with fees 198.86 and separate discount +0.71 in the notification/PDF. Its two workbook cells were reopened and verified. The temporary Central Ave copy was named to match the current mapping (`CENTRAL AVE.xlsx` versus the available `CENTRAL AVE SUNOCO.xlsx`); production configuration was not changed.
- Combined batch notification generation succeeded. Both SUNOCO PDFs were rendered and visually reviewed. Six signed/date scenarios covered zero, discount-only, a gift masked by a larger positive discount, reversal, chargeback, negative discount and January 1/prior-year dating. Three missing required fields and a mismatched control total were rejected before a parsed report could be written.
- All 41 original workbook hashes remained unchanged. No live portal authentication/fetch, scheduler execution or email delivery was exercised. All replay artifacts were temporary; no tests, configuration or production workbooks were modified.
