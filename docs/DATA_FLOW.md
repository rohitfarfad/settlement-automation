# Data flow and contracts

## Dates and identity

All normalized row dates are Python `date`; run timestamps are naive local `datetime`. Supplier names are lowercase in fetch accounts/selection and uppercase in parsed models. Location IDs are strings, including leading zeroes for SUNOCO. Do not coerce them to integers.

| Stage | Date meaning |
| --- | --- |
| Batch date selection | CITGO/SUNOCO: local today minus 1; VALERO: local today; explicit date flags override |
| Fetch `business_date` and raw filename | The caller's requested report date, despite the legacy field name |
| CITGO `ParsedReport.report_date` | `CIT1 ... MM-DD-YY START MSG` header |
| VALERO `ParsedReport.report_date` | `MSR/DTN: MM/DD/YY` header |
| SUNOCO `ParsedReport.report_date` | Maximum `settlementDate` date in JSON `value` |
| Workbook destination | Each normalized row's date, not run date or requested report date |
| Workbook copies/backups | Directory uses the parsed report date from the Excel plan |
| Daily JSON and notification filenames | Requested summary report date (combined preview uses task date) |

`DailyRunSummary.business_date` is a compatibility alias for `report_date`, not a transaction date. Neither `parse_and_validate_supplier_report` nor `validate_report` asserts that detected supplier/header date matches the requested supplier/date. Inspect both during troubleshooting.

## Supplier input to normalized rows

| Supplier | Raw input → extraction → normalized result |
| --- | --- |
| CITGO | DTN visible text → fixed-width detail regex → sum gross/fees/net by location and MMDD date → `DailySettlementTotal` |
| VALERO | DTN visible text → dealer blocks, SUB rows, detail rows and ADJUSTMENTS section → classify each location/date as daily or backdated detail; separate Pay+/monthly/unknown rows → five row collections |
| SUNOCO | Authenticated OData JSON saved as `.txt` → `value` records → settlement date minus one day, dealer fee sign inversion, recomputed net, separate adjustments → daily totals and discounts |

Raw files are `data/raw/{supplier}/YYYY/MM/{supplier}_{requested-date}{source-suffix}`. Production connectors currently return `.txt` for all three suppliers. `DownloadManager` preserves the source suffix, hashes bytes with SHA-256, then copies/moves to a deterministic path. Existing destinations are deleted and replaced; the hash is metadata, not an idempotency key or filename component.

`report_processor.parse_report` normalizes text for dispatch only, then passes the original path to the chosen parser, which rereads UTF-8 with decoding errors ignored. No CSV parser is registered despite `.csv` being permitted by local discovery.

## Important data structures

Models are dataclasses, not Pydantic schemas. Construction itself does not validate financial invariants.

| Structure and source | Creation and fields | Consumers / invariants |
| --- | --- | --- |
| `SupplierAccount`, `config/supplier_accounts.py` | Supplier/portal, username/password env names, format/parser metadata, active flag | Connector factory and supplier resolution; format metadata does not select the parser |
| `StoredRawReport`, `connectors/download_manager.py` | Supplier, portal, requested date, original filename, raw path, SHA-256 and byte count | `FetchResult` and probes; downloaded path may disappear after move |
| `FetchResult`, `ingestion/fetch_reports.py` | Status `success`/`failed`, downloaded paths, stored reports, optional error text | Pipeline; `succeeded` checks status only, then pipeline separately checks raw paths |
| `DailySettlementTotal`, `models.py` | Supplier/location/name/date plus `Decimal` gross, fees, net | Validator, Excel, CSV, email/PDF; expected `gross - fees = net` within 0.01 |
| `MobileAdjustment`, `models.py` | Same monetary triple, optional `source_code` | VALERO aggregation and additive Excel operations; same net invariant |
| `ValeroPayPlusAdjustment`, `models.py` | Date, signed amount, optional source card code | Summaries, supplier-type-specific Excel handling; negative amounts warn |
| `ValeroMonthlyCharge`, `models.py` | Positive absolute amount, assigned date, description | Monthly summary; dealer positive monthly cell/fee adjustment or wholesaler negative monthly cell/net adjustment |
| `UnclassifiedAdjustment`, `models.py` | Optional location/name/amount, report date, description, raw line | Anomaly/email/PDF review; no Excel write or dedicated audit CSV |
| `SunocoCreditCardDiscount`, `models.py` | Date, signed amount, `source_field='adjustments'` | Validation warning, CSV/email/PDF summaries; not an Excel planned value |
| `ParsedReport`, `models.py` | Supplier/report date; required daily/mobile lists; other adjustment lists default empty | Main common boundary from each parser to downstream consumers |
| `ValeroDateBlockStats`, `parsers/valero_parser.py` | Per location/date final SUB/count, POS/CRIND presence, normal detail/card counts | Internal daily-vs-adjustment classifier |
| `ValidationResult` / `ValidationIssue`, `services/validation.py` | `is_valid`, ERROR/WARNING messages | Full daily flow blocks Excel on ERROR; local legacy service does not |
| `ExcelWritePlan` / `ExcelPlannedValue`, `services/excel_writer.py` | Parsed report date, target workbook/date, field/header, Decimal value, source/mode, fee checks | Cell resolution; modes are strings, including `add_to_base` and `add_monthly_charge_to_fee_formula` |
| `ExcelPlanResolution` / `ExcelResolvedValue` | Actual workbook/sheet, header/date row, column/cell, current value, warnings | Apply layer; warning presence is not a global write veto |
| `ExcelAppliedChange` / `ExcelApplyResult` | Old/new values, source/mode, cell, original/output paths, status; counts | Summary counts represent changed/skipped **cells**, not reports/workbooks |
| `RunError`, `DailyRunSummary`, `DailyPipelineResult` | Stage/optional supplier/location/exception type; all subsystem results, warnings/anomalies; optional notification result | Console, artifacts and notification generation |
| `DailyEmailContent`, `EmailAttachment`, `NotificationResult` | Subject/text/HTML; PDF bytes/name/MIME type; sent/mode/provider/paths/error | Graph sender and runners; batch currently omits collected PDF paths from its returned result |

Sources in `connectors/`, `parsers/`, `ingestion/`, `services/`, and `models.py` above are relative to `src/settlement_automation/`.

## Money transformations and aggregation

`utils/money.py::parse_money` removes commas and recognizes trailing `+`/`-`; it does not strip currency symbols or parentheses. CITGO's regex accepts unsigned decimal fields; VALERO regexes require trailing signs. SUNOCO parses JSON floating-point tokens as `Decimal` in the parser, defaults falsey/missing amount fields to zero, and quantizes to cents. Its fetch/save JSON round trips use normal JSON numeric decoding before that parser step.

- CITGO adds every matching detail row into its location/date bucket; repeated input details are not deduplicated.
- VALERO normalizes `fees = -(DISC + FEE)` and retains report gross/net. Non-daily detail rows enter mobile adjustments regardless of card code. Pay+ keeps its signed amount. Monthly billing uses `abs(amount)` and the maximum expected settlement date.
- SUNOCO separates signed discount `totalFiveCentRollback` from aggregate `adjustments`. Daily gross is `totalSalesAmount + adjustments - totalFiveCentRollback`, so all non-discount adjustments affect gross/net. Fees remain `-totalDealerFeeAmount`; net is gross minus fees. The parser requires the adjustment/discount/control fields and checks daily net plus discount against `totalAdjustedNetAmount` at cent precision.
- Reconciliation summaries group by `(supplier, location_id, location_name, date)`, sum `Decimal` amounts and sort by date/location. Mobile and Pay+ summary `source_code` becomes `TOTAL`. Different names for the same location/date can therefore remain separate groups.
- Excel numbers are quantized to cents then converted to float; additive adjustments are visible formulas. There is no general formula calculation engine.

These are implemented transformations, not proof that every supplier input or external accounting convention is covered. See [PARSER_GUIDE](PARSER_GUIDE.md) and [EXCEL_WRITER](EXCEL_WRITER.md).

## Reporting is not workbook reconciliation

Email/PDF transaction totals use card gross + mobile gross for total gross, and card net + mobile net + all Pay+ for total net. They do not apply the Excel dealer/wholesaler Pay+ distinction, deduct monthly charges, or incorporate SUNOCO discounts into those totals. Separate sections show those adjustment categories. Consequently, these display totals are not guaranteed to equal workbook formulas or a bank deposit.

`daily_run_artifacts.py` emits summary/count metadata, fetch statuses/raw paths, per-report row counts, Excel counts/flags/warnings, anomalies, errors, and notification status/preview paths. It does not persist all parsed rows or cell-level changes. JSON dates are ISO strings; Decimal values are strings; paths are strings. `latest.json` is overwritten by each run and, in a completed batch, normally contains only VALERO's second result.

`audit_exporter.export_audit_files` separately writes daily totals, mobile detail/summary, Pay+ detail/summary, monthly detail/summary, SUNOCO discount detail/summary, and validation CSVs. Prefix is `{SUPPLIER}_{parsed-report-date}`; amounts use two decimal places, dates ISO, and empty collections produce empty files. Repeated exports replace those files. Daily processing does not automatically call this exporter.
