# Daily Credit Report Settlement Automation — Fetching Pipeline

This project automates the upstream report collection process for supplier settlement reports. The goal of the fetching pipeline is to replace the manual browser-download/copy step while preserving the existing parser, validation, reconciliation, and Excel/export flow.

The fetching layer is intentionally separate from the parser layer.

```text
Supplier portal
    ↓
Connector logs in and captures raw report
    ↓
DownloadManager stores raw file
    ↓
data/raw/{portal}/{supplier}/YYYY/MM/DD/
    ↓
Official parser pipeline can process the stored raw file
```

---

## Updated Project Structure

```text
prestige-settlement-automation/
│
├── README.md
├── pyproject.toml
├── .env.example
├── .env                         # Local credentials only. Do not commit.
│
├── config/
│   ├── __init__.py
│   ├── settings.py              # Runtime paths and environment-based settings
│   ├── supplier_accounts.py     # Supplier account definitions
│   ├── portal_rules.py          # Portal URLs such as DTN login/DataConnect URL
│   ├── dtn_reports.py           # DTN target report definitions and content markers
│   ├── locations.py             # Location/account mapping
│   ├── supplier_rules.py        # Supplier-specific parsing/business rules
│   └── excel_mapping.py         # Excel/report output mapping
│
├── data/
│   ├── incoming/                # Manual fallback drop-zone
│   │   ├── sunoco/
│   │   ├── citgo/
│   │   └── valero/
│   │
│   ├── raw/                     # Standardized stored raw reports from fetching flow
│   │   ├── sunoco/
│   │   └── dtn/
│   │       ├── citgo/
│   │       └── valero/
│   │
│   ├── processed/
│   ├── failed/
│   ├── backups/
│   └── tmp/                     # Temporary browser captures/downloads
│       ├── dtn/
│       └── parser_input/
│
├── output/
│   ├── reports/                 # Generated reports / audit exports
│   ├── logs/
│   ├── traces/                  # Browser screenshots, HTML, traces on failure
│   ├── audit/
│   └── diagnostics/             # Structured diagnostic JSON records
│
├── state/
│   └── report_runs.sqlite       # Optional future run tracking
│
├── src/
│   └── settlement_automation/
│       │
│       ├── __init__.py
│       ├── cli.py               # Existing CLI
│       ├── cli2.py              # Readable report-preview CLI, if kept locally
│       ├── models.py
│       ├── exceptions.py
│       │
│       ├── connectors/
│       │   ├── __init__.py
│       │   ├── base.py          # SupplierPortalConnector interface
│       │   ├── browser.py       # Playwright browser/session helpers
│       │   ├── credentials.py   # Credential loading from environment variables
│       │   ├── download_manager.py
│       │   ├── dtn_portal.py    # Real DTN connector for CITGO/Valero
│       │   ├── dtn_page.py      # DTN login, DataConnect navigation, row detection
│       │   ├── dtn_capture.py   # DTN visible report-text capture helpers
│       │   ├── dtn_content_selection.py
│       │   ├── dtn_diagnostics.py
│       │   ├── dtn_date.py
│       │   ├── mock_browser_portal.py
│       │   └── sunoco_portal.py # Placeholder/future Sunoco connector
│       │
│       ├── ingestion/
│       │   ├── __init__.py
│       │   └── fetch_reports.py # Fetch orchestration for one or more suppliers
│       │
│       ├── parsers/
│       │   ├── __init__.py
│       │   ├── citgo_parser.py
│       │   ├── valero_parser.py
│       │   └── sunoco_parser.py
│       │
│       ├── services/
│       │   ├── __init__.py
│       │   ├── report_processor.py
│       │   ├── parser_registry.py
│       │   ├── report_detector.py
│       │   ├── validation.py
│       │   ├── reconciliation.py
│       │   ├── excel_writer.py
│       │   ├── audit_exporter.py
│       │   ├── diagnostics.py   # Structured diagnostics writer
│       │   ├── duplicate_check.py
│       │   └── storage.py
│       │
│       └── utils/
│           ├── __init__.py
│           ├── dates.py
│           ├── env.py           # Local .env loader
│           ├── files.py
│           ├── hashing.py
│           ├── logging_utils.py
│           ├── money.py
│           └── text.py          # Text normalization for HTML/plain text reports
│
├── scripts/
│   ├── _path_setup.py
│   ├── fetch_only.py
│   ├── fetch_and_parse_probe.py
│   ├── parse_raw_probe.py
│   ├── probe_dtn_dataconnect.py
│   ├── probe_dtn_click_capture.py
│   ├── probe_dtn_capture.py
│   ├── browser_download_smoke.py
│   ├── process_incoming.py
│   ├── preview_report.py
│   └── run_daily.py
│
└── tests/
    ├── test_connector_factory.py
    ├── test_credentials.py
    ├── test_settings.py
    ├── test_download_manager.py
    ├── test_fetch_reports.py
    ├── test_browser_smoke.py
    ├── test_dtn_reports.py
    ├── test_dtn_date.py
    ├── test_dtn_content_selection.py
    ├── test_citgo_parser.py
    ├── test_valero_parser.py
    ├── test_sunoco_parser.py
    ├── test_reconciliation.py
    └── sample_reports/
        ├── citgo_sample.txt
        ├── valero_sample.txt
        └── sunoco_sample.json
```

---

## Environment Setup

Create a local `.env` file at the project root.

Do not put real credentials in `.env.example`.

```env
# DTN Fuel Buyer portal credentials
DTN_USERNAME=
DTN_PASSWORD=

# DTN portal URLs
DTN_LOGIN_URL=https://fuelbuyer.dtn.com/energy
DTN_DATACONNECT_URL=https://fuelbuyer.dtn.com/energy/common/link.do?contentId=750701&parentId=-1

# Sunoco portal credentials, when implemented
SUNOCO_USERNAME=
SUNOCO_PASSWORD=
SUNOCO_LOGIN_URL=

# Browser automation
HEADLESS_BROWSER=true
DOWNLOAD_TIMEOUT_SECONDS=60
MAX_RETRIES=3
```

Make sure `.env` is ignored by Git:

```gitignore
.env
```

Install browser dependency:

```bash
pip install playwright python-dotenv
python -m playwright install chromium
```

---

## Supplier / Portal Model

The project separates portal access from supplier parsing.

```text
Portal = where/how the report is fetched
Supplier = whose settlement data the report represents
Parser = existing business parser that extracts settlement totals
```

Current supplier setup:

```text
Sunoco
  Portal: Sunoco portal
  Status: connector pending / future implementation

CITGO
  Portal: DTN Fuel Buyer
  DTN tab: DataConnect
  Supplier row: Citgo Petroleum
  Group: Credit Card
  Document: Credit Card Memo

Valero
  Portal: DTN Fuel Buyer
  DTN tab: DataConnect
  Supplier row: Valero R & M
  Group: Credit Card
  Document: Credit Card Memo
```

CITGO and Valero use the same DTN credentials.

---

## DTN Fetch Flow

The working DTN flow is:

```text
1. Open https://fuelbuyer.dtn.com/energy
2. Enter shared DTN credentials
3. Wait until authenticated session is detected
4. Navigate directly to stable DataConnect URL
5. Select the business date from the date dropdown
6. Wait for DataConnect message rows
7. Find rows matching:
   - Supplier
   - Group = Credit Card
   - Document = Credit Card Memo
8. Click candidate row
9. DTN opens report text in the same page
10. Capture visible fixed-width report text
11. Save captured text as .txt
12. DownloadManager stores it under data/raw/
```

The connector should not parse or reconcile anything.

Its job is only:

```text
login → navigate → select date → capture raw report → return local file path
```

---

## CITGO Report Selection Rule

CITGO can have multiple `Credit Card Memo` rows on the same date.

There are at least two possible report bodies:

```text
PREPAID CARD ACTIVATIONS
```

and:

```text
CITGO DAILY RECEIVED TRANSACTION SUMMARY
```

The desired report is the daily transaction summary.

Selection must be content-based, not size-based.

Correct CITGO selection rule:

```text
Accept report if it contains:
CITGO DAILY RECEIVED TRANSACTION SUMMARY

Reject report if it contains:
PREPAID CARD ACTIVATIONS
```

This prevents accidentally processing the prepaid activation report.

---

## Raw File Contract for Fetching

The fetcher should save clean visible report text for CITGO and Valero.

Preferred raw file content:

```text
CITGO PETROLEUM
CIT1  6489  CCM-2649  06-11-26  START MSG
 K4SY              CITGO DAILY RECEIVED TRANSACTION SUMMARY ...
...
```

or:

```text
VALERO
PHB1  3541  CCM-4348  06-12-26  START MSG
JOBBER:   60550 PRESTIGE PETROLEUM COR
MSR/DTN:  06/12/26
...
```

The fetcher must preserve:

```text
- line breaks
- fixed-width spacing
- report headers
- all dealer/detail rows
- total rows
```

Do not wrap or merge lines. The downstream parser depends on line-based regex patterns.

---

## Important Files

### `config/supplier_accounts.py`

Defines active supplier accounts.

Used by the fetching pipeline to determine which connector to use.

```text
sunoco → Sunoco connector
citgo  → DTN connector
valero → DTN connector
```

### `config/portal_rules.py`

Stores portal URLs.

Important DTN values:

```text
DTN_LOGIN_URL
DTN_DATACONNECT_URL
```

The DataConnect URL is currently stable and used after authentication.

### `config/dtn_reports.py`

Defines the DTN report target rows and content markers.

For CITGO, this file should include:

```text
required_content_markers:
  CITGO DAILY RECEIVED TRANSACTION SUMMARY

rejected_content_markers:
  PREPAID CARD ACTIVATIONS
```

### `src/settlement_automation/connectors/base.py`

Defines the connector contract.

Each connector should expose:

```text
fetch_reports(business_date) -> list[Path]
```

The connector returns local temporary raw report paths.

It must not parse, validate, reconcile, or write Excel output.

### `src/settlement_automation/connectors/browser.py`

Central Playwright browser/session helper.

Responsibilities:

```text
- open isolated browser session
- create fresh context per supplier run
- enable downloads
- capture screenshot/HTML on failure
- save traces if enabled
```

Each supplier account should use a fresh browser context so sessions do not leak.

### `src/settlement_automation/connectors/credentials.py`

Loads credentials from environment variables.

It never prints passwords.

### `src/settlement_automation/connectors/dtn_page.py`

Contains DTN page operations:

```text
- login_to_dtn
- wait_for_dtn_authenticated
- open_dataconnect_direct
- select_dataconnect_date
- wait_for_dataconnect_rows
- find_matching_report_rows_by_text
```

This file owns DTN navigation and row detection.

### `src/settlement_automation/connectors/dtn_capture.py`

Contains DTN report capture helpers.

DTN does not provide a normal direct file download for these reports.

The connector clicks the row and captures visible report text from the same page.

### `src/settlement_automation/connectors/dtn_content_selection.py`

Decides whether a captured report body is the intended report.

Used especially for CITGO because multiple Credit Card Memo rows may exist.

### `src/settlement_automation/connectors/download_manager.py`

Stores raw files into standardized storage.

Example output paths:

```text
data/raw/dtn/citgo/2026/06/17/...
data/raw/dtn/valero/2026/06/17/...
data/raw/sunoco/2026/06/17/...
```

It also computes file hashes and avoids duplicate writes.

### `src/settlement_automation/ingestion/fetch_reports.py`

Orchestrates fetching for one or more supplier accounts.

Important behavior:

```text
- calls the correct connector
- stores downloaded/captured files through DownloadManager
- returns FetchResult
- one supplier failure should not break all suppliers
```

### `src/settlement_automation/services/diagnostics.py`

Writes structured JSON diagnostics.

Diagnostics include:

```text
- supplier
- portal
- business date
- failed step
- error message
- traceback
- page URL/title, when browser context exists
- screenshot/HTML/trace paths
- extra debugging metadata
```

### `src/settlement_automation/connectors/dtn_diagnostics.py`

Collects DTN-specific diagnostic information.

Useful when a row is missing or the portal layout changes.

Examples:

```text
- visible rows on page
- matching rows found
```

### `src/settlement_automation/utils/text.py`

Normalizes text for downstream parsing.

Supports:

```text
- plain fixed-width text
- visible copied report text
- simple HTML wrappers containing <pre> report text
```

---

## Common Commands

### Run all tests

```bash
pytest
```

### Run connector/fetching tests

```bash
pytest tests/test_connector_factory.py \
       tests/test_credentials.py \
       tests/test_download_manager.py \
       tests/test_fetch_reports.py
```

### Run browser smoke test

```bash
HEADLESS_BROWSER=false python scripts/browser_download_smoke.py \
  --supplier citgo \
  --business-date 2026-06-17
```

### Probe DTN DataConnect row detection

Use this to verify login, DataConnect navigation, date selection, and row detection.

```bash
HEADLESS_BROWSER=false python scripts/probe_dtn_dataconnect.py \
  --supplier citgo \
  --business-date 2026-06-17 \
  --print-page-text
```

Valero:

```bash
HEADLESS_BROWSER=false python scripts/probe_dtn_dataconnect.py \
  --supplier valero \
  --business-date 2026-06-17 \
  --print-page-text
```

### Probe DTN row-click capture

Use this to manually verify visible report capture from a selected row.

CITGO row 1:

```bash
HEADLESS_BROWSER=false python scripts/probe_dtn_click_capture.py \
  --supplier citgo \
  --business-date 2026-06-17 \
  --row-number 1 \
  --pause-after-click
```

CITGO row 2:

```bash
HEADLESS_BROWSER=false python scripts/probe_dtn_click_capture.py \
  --supplier citgo \
  --business-date 2026-06-17 \
  --row-number 2 \
  --pause-after-click
```

Valero row 1:

```bash
HEADLESS_BROWSER=false python scripts/probe_dtn_click_capture.py \
  --supplier valero \
  --business-date 2026-06-17 \
  --row-number 1 \
  --pause-after-click
```

### Fetch only

Runs the connector and stores raw files.

Does not parse or validate.

```bash
HEADLESS_BROWSER=false python scripts/fetch_only.py \
  --supplier citgo \
  --business-date 2026-06-17
```

Valero:

```bash
HEADLESS_BROWSER=false python scripts/fetch_only.py \
  --supplier valero \
  --business-date 2026-06-17
```

Expected output:

```text
[SUCCESS] supplier=citgo portal=dtn business_date=2026-06-17
  raw_path=...
  hash=...
  size_bytes=...
```

### Parse a captured raw file

Used to test one raw file manually.

```bash
python scripts/parse_raw_probe.py \
  --file data/tmp/dtn/citgo/2026-06-17/citgo_click_capture_2026-06-17_row_2.txt
```

### Fetch and parse compatibility probe

Runs fetch and then checks compatibility with the official parser/validation pipeline.

```bash
HEADLESS_BROWSER=false python scripts/fetch_and_parse_probe.py \
  --supplier citgo \
  --business-date 2026-06-17
```

Valero:

```bash
HEADLESS_BROWSER=false python scripts/fetch_and_parse_probe.py \
  --supplier valero \
  --business-date 2026-06-17
```

### Readable report preview CLI

If using `cli2.py`:

```bash
python src/settlement_automation/cli2.py \
  --file data/tmp/dtn/citgo/2026-06-17/citgo_click_capture_2026-06-17_row_2.txt
```

Example output sections:

```text
REPORT SUMMARY
DAILY TOTALS
BACKDATED MOBILE ADJUSTMENTS
BACKDATED MOBILE ADJUSTMENTS SUMMARY
VALIDATION
```

---

## Diagnostics

Diagnostics are written under:

```text
output/diagnostics/{supplier}/{business_date}/
```

Browser failure artifacts are written under:

```text
output/traces/
```

A diagnostic JSON may include:

```text
supplier_name
portal_name
business_date
step_name
status
message
page_url
page_title
screenshot_path
html_path
trace_path
traceback_text
extra
```

For DTN failures, `extra` may include:

```text
visible_rows
matching_rows
raw_path
file_hash
size_bytes
validation_issues
```

### Intentional failure test

Use a date where no report exists:

```bash
HEADLESS_BROWSER=false python scripts/fetch_and_parse_probe.py \
  --supplier citgo \
  --business-date 2026-04-24
```

Then inspect diagnostics:

```bash
ls -lh output/diagnostics/citgo/2026-04-24/
```

---

## Current Working Status

Confirmed working:

```text
- DTN credentials load from .env
- Browser launches through Playwright
- DTN login succeeds without MFA/CAPTCHA
- Authenticated session is detected after login
- Direct DataConnect URL opens after authentication
- Date dropdown selection works
- DTN rows can be detected for CITGO and Valero
- DTN report row click opens report in same page
- Visible fixed-width report text can be captured
- Captured CITGO daily transaction report parses successfully
- Validation passes for captured CITGO row 2
- Diagnostics are generated on failure
```

Known CITGO behavior:

```text
For 2026-06-17, CITGO had two Credit Card Memo rows:
- row 1: prepaid card activations
- row 2: daily received transaction summary

The correct row should be selected by report content markers, not file size.
```

Known Valero behavior:

```text
For 2026-06-17, Valero had one Credit Card Memo row.
If multiple Valero Credit Card Memo rows appear later, add content markers in config/dtn_reports.py.
```

---

## Next Development Steps

### 1. Finalize real DTN connector

Make sure `DTNPortalConnector` uses content-based report selection:

```text
Find all matching rows
Open each report
Capture visible text
Accept only report matching required markers
Reject reports matching rejected markers
Return accepted raw .txt path
```

### 2. Run full fetch-only checks

```bash
HEADLESS_BROWSER=false python scripts/fetch_only.py \
  --supplier citgo \
  --business-date 2026-06-17

HEADLESS_BROWSER=false python scripts/fetch_only.py \
  --supplier valero \
  --business-date 2026-06-17
```

### 3. Run fetch-and-parse compatibility checks

```bash
HEADLESS_BROWSER=false python scripts/fetch_and_parse_probe.py \
  --supplier citgo \
  --business-date 2026-06-17

HEADLESS_BROWSER=false python scripts/fetch_and_parse_probe.py \
  --supplier valero \
  --business-date 2026-06-17
```

### 4. Add scheduler-level orchestration

After DTN is stable:

```text
scripts/run_daily.py
  ↓
fetch all active suppliers
  ↓
store raw reports
  ↓
run parse/validation
  ↓
later write Excel/report output
```

### 5. Implement Sunoco connector

Sunoco is separate from DTN.

Sunoco raw-file requirement:

```text
Save valid JSON response text.
Do not save browser-rendered [object Object].
```

### 6. Add run-state tracking

Add tracking for:

```text
supplier
business_date
status
raw_path
file_hash
started_at
finished_at
diagnostic_path
```

This can start as SQLite under:

```text
state/report_runs.sqlite
```

### 7. Productionize

Before unattended daily runs:

```text
- run headless
- add retries
- add notification email/slack
- verify .env deployment handling
- ensure screenshots/HTML do not expose credentials
- rotate DTN credentials if needed
- add cleanup policy for output/traces and data/tmp
```
