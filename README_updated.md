# Prestige Settlement Automation — Fetching and Parser Pipeline

This project automates the upstream report collection and parsing process for supplier settlement reports. The fetching pipeline replaces the manual browser-download/copy step, while the parser pipeline converts raw supplier reports into normalized settlement objects used by validation, reconciliation, audit exports, and later Excel updates.

The fetching layer is intentionally separate from the parser layer. Connectors fetch and store raw files only; parsers read those raw files and extract settlement totals.

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

## Parser Pipeline Overview

The parser pipeline is the official downstream consumer of stored raw reports.

The fetching pipeline should not call supplier-specific parsers directly. It should save the raw file and call the single parser entrypoint:

```python
from settlement_automation.services.report_processor import parse_report

report = parse_report(raw_file_path)
```

The parser pipeline then handles supplier detection, parsing, normalization, validation, reconciliation, and optional audit CSV exports.

```text
Raw report file
    ↓
services/report_processor.py::parse_report(file_path)
    ↓
utils/text.py::load_normalized_text(file_path)
    ↓
services/parser_registry.py::get_parser_for_text(text)
    ↓
Supplier-specific parser
    ├── parsers/citgo_parser.py::parse_citgo_report(file_path)
    ├── parsers/valero_parser.py::parse_valero_report(file_path)
    └── parsers/sunoco_parser.py::parse_sunoco_report(file_path)
    ↓
models.py::ParsedReport
    ↓
services/validation.py::validate_report(report)
    ↓
services/reconciliation.py for mobile adjustment summaries
    ↓
services/audit_exporter.py for CSV audit files
    ↓
Later: services/excel_writer.py
```

### Parser Entry Point

File:

```text
src/settlement_automation/services/report_processor.py
```

Function:

```python
parse_report(file_path: str) -> ParsedReport
```

Responsibilities:

```text
1. Load and normalize raw file text.
2. Pass normalized text to parser registry.
3. Select exactly one matching supplier parser.
4. Execute the selected parser.
5. Return a normalized ParsedReport object.
```

Expected implementation shape:

```python
from settlement_automation.models import ParsedReport
from settlement_automation.services.parser_registry import get_parser_for_text
from settlement_automation.utils.text import load_normalized_text


def parse_report(file_path: str) -> ParsedReport:
    text = load_normalized_text(file_path)
    parser = get_parser_for_text(text)
    return parser.parser(file_path)
```

The fetching pipeline should treat this function as the parser boundary.

### Parser Registry

File:

```text
src/settlement_automation/services/parser_registry.py
```

Main function:

```python
get_parser_for_text(text: str) -> RegisteredParser
```

The registry maps supplier detection rules to parser functions.

```text
CITGO  → parse_citgo_report
VALERO → parse_valero_report
SUNOCO → parse_sunoco_report
```

Current detection is content-based, not extension-based.

Expected detectors:

```text
CITGO:
  must contain CITGO PETROLEUM
  must contain CITGO DAILY RECEIVED TRANSACTION SUMMARY

VALERO:
  must contain VALERO
  must contain JOBBER
  must contain DEALER CREDITS

SUNOCO:
  must contain JSON text with Sunoco settlement fields, such as:
  SettlementSummary / settlementDate / totalSalesAmount / totalDealerFeeAmount / shipToNumber
```

Registry behavior:

```text
0 matches  → raise ValueError("No matching parser found for this report")
1 match    → return selected parser
2+ matches → raise ValueError("Multiple parsers matched this report")
```

This prevents a raw file from being silently parsed by the wrong supplier parser.

---

## Parser Output Model

All supplier parsers return the same normalized object model.

File:

```text
src/settlement_automation/models.py
```

Classes:

```python
@dataclass
class DailySettlementTotal:
    supplier: str
    location_id: str
    location_name: str
    date: date
    gross_amt: Decimal
    fees: Decimal
    net_amt: Decimal
```

```python
@dataclass
class MobileAdjustment:
    supplier: str
    location_id: str
    location_name: str
    date: date
    gross_amt: Decimal
    fees: Decimal
    net_amt: Decimal
    source_code: str | None = None
```

```python
@dataclass
class ParsedReport:
    supplier: str
    report_date: date
    daily_totals: list[DailySettlementTotal]
    mobile_adjustments: list[MobileAdjustment]
```

Important model rules:

```text
- location_id should be a string for all suppliers.
- This preserves SUNOCO leading-zero IDs such as 0326461100.
- fees are normalized as positive deduction amounts.
- validation always checks gross_amt - fees == net_amt.
```

Downstream code should use only:

```python
report.supplier
report.report_date
report.daily_totals
report.mobile_adjustments
```

---

## Supplier-Specific Parser Behavior

### CITGO Parser

File:

```text
src/settlement_automation/parsers/citgo_parser.py
```

Function:

```python
parse_citgo_report(file_path: str) -> ParsedReport
```

Input type:

```text
Plain fixed-width report text, or simple HTML/pre text containing the report body.
```

Extraction flow:

```text
1. Read raw report text.
2. Extract report date from START MSG line.
3. Parse fixed-width detail rows.
4. Aggregate detail rows by location_id + transaction date.
5. Create DailySettlementTotal rows.
6. Return ParsedReport with no mobile_adjustments.
```

Important CITGO regex targets:

```text
CIT1 ... MM-DD-YY START MSG
LOCATION TERM BATCH DATE COUNT TYPE GROSS AMT FEES NET AMT
```

CITGO field mapping:

```text
location_id   = first column, for example 15861002
date          = row MMDD column, for example 0610
gross_amt     = GROSS AMT
fees          = FEES
net_amt       = NET AMT
location_name = config.locations.CITGO_LOCATIONS[location_id]
```

CITGO uses the row date as the business date. The year comes from the report START MSG date.

CITGO does not currently produce mobile adjustments.

### Valero Parser

File:

```text
src/settlement_automation/parsers/valero_parser.py
```

Function:

```python
parse_valero_report(file_path: str) -> ParsedReport
```

Input type:

```text
Plain fixed-width report text, or simple HTML/pre text containing the report body.
```

Extraction flow:

```text
1. Read raw report text.
2. Extract report date from MSR/DTN line.
3. Parse DEALER blocks to track location_id and location_name.
4. Parse SUB MMDD rows to find daily dealer totals.
5. Infer current business date as max SUB date in the report.
6. Create DailySettlementTotal rows from current-business-date SUB rows.
7. Parse older mobile detail rows as MobileAdjustment rows.
```

Valero daily total mapping:

```text
location_id   = current DEALER number
location_name = current DEALER name
date          = SUB MMDD date
gross_amt     = SUB row GROSS
fees          = -(DISC + FEE)
net_amt       = SUB row NET
```

Valero mobile adjustment rule:

```text
If a detail row has transaction date earlier than current_business_date
and card code is in config.supplier_rules.VALERO_MOBILE_CODES,
create a MobileAdjustment for the older date.
```

Current mobile codes:

```python
VALERO_MOBILE_CODES = {
    "VPVA",
    "VPVS",
    "VPMC",
    "VPAX",
    "VPVP",
}
```

These backdated mobile adjustments are not part of the current-day Excel row. They should later update the previous business date row, usually in `MOBILE PAY ADDED TO GROSS/NET`.

### SUNOCO Parser

File:

```text
src/settlement_automation/parsers/sunoco_parser.py
```

Function:

```python
parse_sunoco_report(file_path: str) -> ParsedReport
```

Input type:

```text
Raw JSON text saved from the Sunoco portal.
```

Expected JSON shape:

```json
{
  "value": [
    {
      "settlementDate": "2026-06-17T00:00:00",
      "totalSalesAmount": 10461.02,
      "totalDealerFeeAmount": -221.05,
      "totalAdjustedNetAmount": 10241.15,
      "location": {
        "shipToNumber": "0326461100",
        "shipToCustomerName": "CENTRAL AVE SUNOCO"
      }
    }
  ]
}
```

Extraction flow:

```text
1. Read raw JSON text.
2. Load JSON using json.loads(..., parse_float=Decimal).
3. Iterate over records in data["value"].
4. Extract location.shipToNumber as location_id.
5. Extract location.shipToCustomerName as location_name.
6. Extract settlementDate.
7. Compute business date as settlementDate - 1 day.
8. Use totalSalesAmount as gross_amt.
9. Use -totalDealerFeeAmount as fees.
10. Compute net_amt as gross_amt - fees.
11. Return ParsedReport with no mobile_adjustments.
```

Important SUNOCO rules:

```text
- settlementDate is the settlement date, not the business date.
- business date = settlementDate - 1 day.
- Use net before loyalty/adjusted-net effects.
- Do not use totalAdjustedNetAmount for Excel net amount.
- Use totalSalesAmount and totalDealerFeeAmount instead.
```

SUNOCO field mapping:

```text
location_id   = location.shipToNumber
location_name = location.shipToCustomerName
date          = settlementDate - 1 day
gross_amt     = totalSalesAmount
fees          = -totalDealerFeeAmount
net_amt       = gross_amt - fees
```

SUNOCO does not currently produce mobile adjustments.

---

## Validation, Reconciliation, and Audit Exports

### Validation

File:

```text
src/settlement_automation/services/validation.py
```

Function:

```python
validate_report(report: ParsedReport) -> ValidationResult
```

Validation checks:

```text
- daily_totals is not empty
- no duplicate supplier + location_id + date daily rows
- no UNKNOWN location names
- gross_amt - fees == net_amt for daily totals
- gross_amt - fees == net_amt for mobile adjustments
```

A validation failure should block Excel writing.

### Reconciliation / Mobile Summary

File:

```text
src/settlement_automation/services/reconciliation.py
```

Functions:

```python
summarize_mobile_adjustments(rows: list[MobileAdjustment]) -> list[MobileAdjustment]
get_mobile_adjustment_grand_total(rows)
```

`summarize_mobile_adjustments` groups mobile adjustments by:

```text
supplier + location_id + location_name + date
```

Use detail rows for audit. Use summary rows for Excel updates.

### Audit CSV Export

File:

```text
src/settlement_automation/services/audit_exporter.py
```

Function:

```python
export_audit_files(
    report: ParsedReport,
    validation_result: ValidationResult,
    output_dir: str = "output/reports",
) -> list[Path]
```

Generated files:

```text
{SUPPLIER}_{report_date}_daily_totals.csv
{SUPPLIER}_{report_date}_mobile_adjustments_detail.csv
{SUPPLIER}_{report_date}_mobile_adjustments_summary.csv
{SUPPLIER}_{report_date}_validation.csv
```

Audit exports should be produced before Excel writing so a developer can trace every number back to the parser output.

---

## Fetch-to-Parser Integration Contract

The fetcher should save the raw report and pass the saved path to the parser pipeline.

Minimal integration pattern:

```python
from pathlib import Path

from settlement_automation.services.report_processor import parse_report
from settlement_automation.services.validation import validate_report
from settlement_automation.services.audit_exporter import export_audit_files


def fetch_and_parse_supplier_report(raw_text_or_bytes, output_path: str):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(raw_text_or_bytes, bytes):
        path.write_bytes(raw_text_or_bytes)
    else:
        path.write_text(raw_text_or_bytes, encoding="utf-8")

    report = parse_report(str(path))
    validation_result = validate_report(report)
    export_audit_files(report, validation_result)

    if not validation_result.is_valid:
        raise ValueError(validation_result.issues)

    return report
```

The fetcher should not:

```text
- parse supplier data itself
- filter out old Valero rows before parsing
- convert SUNOCO location IDs to integers
- save browser-rendered [object Object] instead of JSON
- wrap or merge CITGO/Valero fixed-width lines
```

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

### Official parser preview CLI

Run parser, validation, mobile-adjustment summary, and optional audit exports for any supported supplier.

CITGO:

```bash
python -m settlement_automation.cli \
  --file data/raw/dtn/citgo/2026/06/17/<captured_report>.txt \
  --preview \
  --export-csv
```

Valero:

```bash
python -m settlement_automation.cli \
  --file data/raw/dtn/valero/2026/06/17/<captured_report>.txt \
  --preview \
  --export-csv
```

SUNOCO:

```bash
python -m settlement_automation.cli \
  --file data/raw/sunoco/2026/06/17/<raw_sunoco_response>.json \
  --preview \
  --export-csv
```

Expected output sections:

```text
Supplier
Report Date
DAILY TOTALS
BACKDATED MOBILE ADJUSTMENTS
BACKDATED MOBILE ADJUSTMENTS SUMMARY
VALIDATION
EXPORTED AUDIT FILES
```

### Parser-only raw probe

Use this when debugging parser compatibility for one captured raw file.

```bash
python scripts/parse_raw_probe.py \
  --file data/tmp/dtn/citgo/2026-06-17/citgo_click_capture_2026-06-17_row_2.txt
```

The probe should call the official parser entrypoint:

```python
settlement_automation.services.report_processor.parse_report
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


Parser pipeline confirmed working:

```text
- Parser registry detects VALERO, CITGO, and SUNOCO by raw file contents
- VALERO parser extracts current-day SUB totals
- VALERO parser extracts backdated mobile adjustments and summary totals
- CITGO parser extracts location/date daily totals from fixed-width transaction rows
- SUNOCO parser reads JSON text saved from portal
- SUNOCO parser converts settlementDate to business date by subtracting one day
- SUNOCO parser uses totalSalesAmount and totalDealerFeeAmount for pre-loyalty net
- All parsers return the shared ParsedReport model
- Generic validation works across all suppliers
- Audit CSV export works after parsing
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

### 4. Keep parser tests current

Add or update parser tests whenever a supplier report format changes.

```bash
pytest tests/test_citgo_parser.py \
       tests/test_valero_parser.py \
       tests/test_sunoco_parser.py \
       tests/test_reconciliation.py
```

Parser tests should verify:

```text
- supplier detection
- report date extraction
- business date calculation
- location ID and name extraction
- gross / fees / net extraction
- validation pass/fail behavior
- Valero mobile adjustment detail and summary totals
- SUNOCO leading-zero location IDs remain strings
```

### 5. Add Excel writer after parser validation remains stable

Excel writing should come after:

```text
fetch raw report
parse report
validate report
export audit CSVs
confirm no validation errors
```

Excel writer should consume only normalized objects:

```python
report.daily_totals
summarize_mobile_adjustments(report.mobile_adjustments)
```

It should not read raw supplier reports directly.

### 6. Add scheduler-level orchestration

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

### 7. Implement Sunoco connector

Sunoco is separate from DTN.

Sunoco raw-file requirement:

```text
Save valid JSON response text.
Do not save browser-rendered [object Object].
```

### 8. Add run-state tracking

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

### 9. Productionize

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
