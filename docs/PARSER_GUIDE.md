# Parser guide

The parser boundary is `src/settlement_automation/services/report_processor.py::parse_report(file_path)`. It returns the dataclasses in `src/settlement_automation/models.py`; there is no later generic normalization pass. Preserve supplier-specific rules rather than inferring meaning from shared field names.

## Dispatch and shared utilities

`parse_report` calls `utils/text.py::load_normalized_text`, then `services/parser_registry.py::get_parser_for_text`. Exactly one detector must match; zero or multiple matches raise `ValueError`.

| Parser | Required content, case-insensitive |
| --- | --- |
| `parsers/valero_parser.py::parse_valero_report` | `VALERO`, `JOBBER`, `DEALER CREDITS` |
| `parsers/citgo_parser.py::parse_citgo_report` | `CITGO PETROLEUM`, `CITGO DAILY RECEIVED TRANSACTION SUMMARY` |
| `parsers/sunoco_parser.py::parse_sunoco_report` | `SettlementSummary`, `settlementDate`, `totalSalesAmount`, `totalAdjustedNetAmount`, `shipToNumber` |

Paths in this guide beginning `parsers/`, `services/`, or `utils/` are under `src/settlement_automation/`. `services/report_detector.py::detect_supplier` delegates to the registry. `parsers/base.py` is empty; the registry holds callable functions, not subclasses. `SupplierAccount.parser_name` is metadata and does not override content selection.

The shared text loader reads UTF-8 with `errors='ignore'`, unescapes HTML entities, replaces nonbreaking spaces, normalizes line endings, removes common table/pre/html/body wrapper tags, and replaces form feeds with newlines. **This cleaned text is used only for detection.** Each supplier parser rereads the original file with `errors='ignore'`. A wrapper may pass detection and still not parse like plain text.

`utils/money.py::parse_money` strips whitespace/commas; `123.45-` becomes a negative Decimal and `123.45+` positive. Plain Decimal syntax also works at helper level. Dollar signs, parentheses, empty strings and invalid numbers are not repaired. The actual parser regexes further restrict accepted input. `utils/dates.py` uses `strptime`: MMDD plus a supplied year, or MM/DD/YY after replacing hyphens. Invalid dates raise exceptions.

Parsers do not return warning lists. Unmatched text is generally skipped; validation and summary anomalies provide downstream warnings. A successful parse is not proof of complete extraction.

## CITGO: fixed-width daily received transaction summary

Source: `parsers/citgo_parser.py` and `config/locations.py::CITGO_LOCATIONS`.

```text
raw DTN text -> START MSG date and matching detail lines
 -> sum by location/date -> DailySettlementTotal -> validate/Excel/CSV/email/PDF
```

1. `REPORT_DATE_RE` extracts `MM-DD-YY` from `CIT1`, a number, a nonspace token, then the date and `START MSG`. Missing header raises `ValueError`.
2. `DETAIL_ROW_RE` matches line start: eight-digit location ID, two-digit terminal, two-digit batch, four-digit MMDD, integer count, uppercase/slash transaction type, then unsigned gross/fees/net with two decimal places and optional commas. It is not end-anchored.
3. Terminal, batch, count, and transaction type are matched but discarded; there is no type-specific sign/classification rule. Every matching row contributes to a `(location_id, date)` sum.
4. Transaction year is always the report year. Unlike VALERO, there is no previous-year adjustment when MMDD is later than the report date.
5. Names come from `CITGO_LOCATIONS`, falling back to literal `UNKNOWN`. Results sort by date/location and return supplier `CITGO`, with no mobile or other adjustment lists populated.

**Assumptions and failure boundaries:** signed detail amounts do not match the regex; other headers/subtotals/unmatched lines are ignored without a parser warning. Duplicate raw detail lines are summed, not detected. A header-only report returns an empty daily list and then fails validation. December transactions in a January report are assigned January's year. No report-level control-total reconciliation occurs.

Downstream, Excel treats only the latest daily date in a CITGO report as replacement values. Older normalized daily dates become additive `backdated_daily_total` writes. This classification happens in the Excel writer, not the CITGO parser.

**Tests:** `tests/test_citgo_parser.py` and `tests/sample_reports/citgo_sample.txt` are empty. `tests/test_dtn_content_selection.py` covers report selection, not financial extraction. Representative signed/year-boundary and duplicate inputs are **Needs verification**.

## VALERO: dealer blocks and adjustment sections

Source: `parsers/valero_parser.py`, `config/supplier_rules.py`.

```text
raw DTN text -> report date + SUB dates + per-location structural statistics
 -> daily-date classification -> SUB daily totals / non-daily detail adjustments
 -> Pay+, monthly and unclassified rows -> ParsedReport -> downstream consumers
```

### Header, dates, and block interpretation

`MSR_RE` requires `MSR/DTN: MM/DD/YY`; missing it raises `ValueError`. `DEALER_RE` starts a location block with an ID and name and resets the inherited detail date. Report names come from these blocks, not `config/locations.py`.

`parse_valero_mmdd` first parses MMDD in the report year, then uses the prior year if that date is later than the report date. This protects December/January rollover, but applies to any future MMDD, not just December. Initial invalid-date parsing can still raise before fallback.

`collect_valero_sub_dates` extracts all dated final `SUB MMDD count gross disc fee net` rows. `get_valero_settlement_dates` chooses:

- Monday report: available dates among the previous Friday/Saturday/Sunday.
- Other weekdays and weekends: the previous calendar day, if available.
- If no expected date exists: the latest available date strictly before the report date.
- No eligible date: `ValueError('No Valero settlement dates found')`.

This is a calendar rule, not a business-holiday calendar. A partial Monday set is accepted if any expected dates match.

`collect_valero_date_block_stats` records final SUB presence/count, detail rows, non-mobile card varieties, POS card varieties, and `SUB POS` / `SUB CRIND` presence by `(location_id, transaction_date)`. Detail rows without MMDD inherit the most recent detail date in that dealer block. `SUB POS/CRIND` attaches to that inherited date. `SUB_DATE_RE` dates do not themselves update the inherited detail date.

`find_valero_daily_dates_by_location` requires a final dated SUB, then classifies that block as daily if its date is expected **or** `looks_like_late_full_daily_settlement` matches one of:

| Complete-block signal | Threshold |
| --- | --- |
| POS section | At least 4 normal detail rows and at least 2 normal POS card codes |
| POS and CRIND sections | At least 5 normal detail rows and at least 3 normal card codes |
| CRIND section | Final SUB count at least 20, at least 5 normal detail rows and at least 3 normal card codes |

Normal here excludes `VALERO_MOBILE_CODES` (`VPVA`, `VPVS`, `VPMC`, `VPAX`, `VPVP`, `VALP`, `VPAY`) and any code beginning `VP`. These exclusions affect the heuristic, not the final mobile bucket's eligibility. The heuristic has no separate strict “older date” condition; its purpose is documented as detecting late full settlements. No daily location/date after this pass raises `ValueError`.

### Main extraction and sign conventions

| Input | Output and meaning |
| --- | --- |
| Final dated `SUB` classified daily for that location | One `DailySettlementTotal`: gross/net retain signs; `fees = -(disc + fee)` |
| Detail row whose inherited date is not daily for that location | `MobileAdjustment`, same monetary rule, source card code retained; **any** matching card code can enter |
| Detail row on a daily date | Not separately output; final SUB already supplies that day's total |
| `SUB POS`, `SUB CRIND`, overall TOTAL/header lines | Structural/statistical use or ignored; not extra daily values |

Financial regexes require commas/digits, exactly two decimal places, and a trailing sign. Detail rows require uppercase IO/card/transaction tokens; the dated prefix is optional. Matched signed negative fees normally normalize positive. A source positive DISC/FEE can normalize negative; do not silently replace with `abs`.

Daily totals and mobile details are retained as lists, not deduplicated. Repeated daily SUBs are caught later by validation's supplier/location/date key. Repeated mobile details and adjustment rows are not generally deduplicated by validation.

### Adjustment section and classifications

An `ADJUSTMENTS` line enters section mode; `TOTAL ADJUSTMENTS` exits it. Blank lines and the `DEALER DESCRIPTION ADJUSTMENT AMT` header are skipped.

1. **Pay+:** `location CRND CARD VP+ Fuel Offer MM-DD amount±`. Recognized inside and outside the section. `is_valero_payplus_code` always returns True because the row regex determines the category; VISA and other matched codes are accepted. `VALERO_PAYPLUS_CODES` is not a restriction. Amount remains signed; date uses year fallback. Name is taken from a previously seen dealer or `UNKNOWN`.
2. **Monthly charge:** `location MONTHLY description BILLING amount±`, case-insensitive, recognized **inside the section only**. Output amount is absolute (positive fee); date is `max(expected_settlement_dates)`, not the latest heuristic-promoted date. Description is reconstructed as `MONTHLY ... BILLING`.
3. **Unclassified:** inside the section only, exactly five-digit location, description, signed amount at end of line. Preserve report date, signed amount, description, and raw line. Amount helper can return `None` on conversion failure, although the regex already restricts numeric syntax.
4. Other lines in the section are silently skipped. Monthly/unknown rows outside the section are also skipped. Thus “unclassified” is not a catch-all for every unrecognized line.

Lists sort by date/location and applicable source/description. Monthly/Pay+ names can be `UNKNOWN` if the dealer block has not appeared earlier. Unclassified rows become `UNCLASSIFIED_ADJUSTMENT` anomalies in summary construction, not blocking validation errors or Excel writes.

**Downstream:** aggregate mobile triples before adding to prior workbook rows; aggregate Pay+ before dealer/wholesaler-specific writing; aggregate monthly charges before fee modification. All VALERO daily dates, including late full settlements, use normal SET planning. See [EXCEL_WRITER](EXCEL_WRITER.md).

### Existing VALERO tests

`tests/test_valero_parser.py` has four inline synthetic tests:

- Pay+ with VISA outside the section passes.
- A mixed prior mobile/current daily report with section Pay+ passes and excludes TOTAL rows from unclassified output.
- Unknown-adjustment and monthly-charge tests omit `ADJUSTMENTS`; both fail against the current section-only implementation.

`tests/sample_reports/valero_sample.txt` is empty. Tests call the supplier parser directly, so they do not cover registry requirements such as `JOBBER`. No automated coverage proves Monday/year rollover, late-full-day thresholds, monthly assignment, duplicate handling, or malformed block recovery.

## SUNOCO: JSON settlement summary

Source: `parsers/sunoco_parser.py`; fetch contracts: `connectors/sunoco_api.py`, `sunoco_capture.py`, `sunoco_date.py`.

```text
SettlementSummary JSON value[] -> location + settlementDate + monetary fields
 -> prior-day daily totals and separate discounts -> ParsedReport -> validation/output
```

The parser uses `json.loads(text, parse_float=Decimal)` and requires a nonempty top-level `value`. Missing/empty `value` raises `ValueError`. There is no comprehensive shape schema; wrong types and malformed dates can raise ordinary exceptions.

For each record:

- `location` defaults to `{}` if falsey. `shipToNumber` is stringified/trimmed and must be nonempty; absent/empty raises. Explicit JSON null stringifies to `None`, which is nonempty; that is not separately rejected. `shipToCustomerName` is stringified/trimmed, defaulting to empty string.
- Required `settlementDate` is parsed by `datetime.fromisoformat(...).date()`; the date is taken directly without timezone conversion. Output transaction date is minus one day.
- `to_decimal(value)` is `Decimal(str(value or 0)).quantize(Decimal('0.01'))`; absent/null/empty/false amounts become zero. Malformed numeric strings raise.
- Gross is `totalSalesAmount`; normalized fees are the negative of `totalDealerFeeAmount`; net is recomputed as gross minus fees. `totalAdjustedNetAmount` is only a detector/fetch marker, not a parsed control total.
- Every record also creates a `SunocoCreditCardDiscount` from `adjustments`, preserving its sign and including zero. It is not folded into daily net or currently written to Excel.

No same-location/date aggregation occurs in the parser. Duplicated records generate duplicate daily rows, which validation rejects. Daily rows sort by date/location; discount rows retain input order. `ParsedReport.report_date` is the maximum settlement date, not a guarantee of a single-date response. A blank name is not literal `UNKNOWN`, so the validator's unknown-name check does not warn for it.

The fetch helper currently requests exactly the caller's date. For requested report date `2026-07-06`, a JSON settlement date of July 6 produces a July 5 workbook row. The `portal_request_date_rule` string in `config/sunoco_reports.py` and both tests in `tests/test_sunoco_date.py` still describe adding a day and conflict with source.

**Tests:** there is no `tests/test_sunoco_parser.py`. API and capture tests cover pagination, headers, JSON markers and saving, not normalized financial rows. Null fields, duplicate records, missing amounts, negative adjustments and timezone/date boundaries lack dedicated parser tests.

## Validation, warnings, and safe changes

`services/validation.py::validate_report` checks nonempty daily totals, duplicate daily keys, and daily/mobile `gross - fees = net` within 0.01. Literal `UNKNOWN` names warn. Negative Pay+, monthly amounts, and SUNOCO discounts warn; negative daily gross/fees/net are not independently forbidden. Unknown adjustments are not checked here.

`services/anomaly_detector.py` adds warnings for retained unclassified adjustments, and for daily rows from a prior month when **run day > 10**. These are reporting rules; the full pipeline constructs anomalies after Excel processing and does not use them as a write veto. Historical reruns can trigger the prior-month warning.

Before a parser change, trace the entire path through validation, reconciliation, Excel and notification totals. Preserve raw evidence and make skipped/unclassified behavior explicit. Use isolated representative inputs and existing tests, documenting the failing baseline. Input completeness, portal date accuracy and production control totals remain **Needs verification**; no parser currently proves them comprehensively.
