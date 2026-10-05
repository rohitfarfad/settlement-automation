# Excel writer

Entry point: `src/settlement_automation/services/excel_writer.py::write_parsed_report_to_excel`. It uses openpyxl, not Excel COM or an Excel desktop process. All helper names below refer to this module unless another source is given.

## Plan, resolve, apply

1. `build_excel_write_plan` converts normalized rows into `ExcelPlannedValue` objects, with supplier/location/date target, field/header, Decimal value, source and mode. It performs fee-math checks.
2. `resolve_excel_write_plan_targets` finds each workbook/sheet/date/header and captures current cell values. It loads each workbook twice: formula mode and cached-value mode.
3. `apply_excel_write_plan` prepares copies/backups, opens target workbooks, applies groups in order, then saves each workbook.
4. The public function prints plan/resolution/change previews and returns `ExcelWriteResult` with warnings and cell counts.

The function defaults to `dry_run=True`. Daily runner flags explicitly determine that argument: `--write-excel` without `--excel-dry-run` applies writes, to copies unless `--write-originals` is set. The scheduled PowerShell wrapper requests original writes by default. The writer itself does not call `validate_report`; callers must establish validation. Full daily flow and workbook probes gate invalid reports, while the older local parse/write/notify service does not.

## Workbook identity and target resolution

`config/excel_mapping.py::get_workbook_filename` resolves supplier/location/year overrides, then name override, then `config/locations.py` office name, then parser location-name fallback. General filename: `{transaction-year} CC {mapped-location-name}.xlsx`. It does **not** automatically append/strip the supplier from the mapped name. The supplied report name does not outrank a known location ID.

The current explicit filename override is for the 2026 SUNOCO Aviation Rd workbook with two spaces after `CC`. Read `WORKBOOK_FILENAME_OVERRIDES` rather than guessing filenames. VALERO location IDs must be classified in `VALERO_DEALER_LOCATIONS` or `VALERO_WHOLESALER_LOCATIONS`. Planning checks all daily, mobile, Pay+ and monthly records first. An unclassified location produces one warning with its ID, name and configuration instructions; all Excel writes for that location are skipped while configured locations continue. Classification is never guessed, and no partial daily/adjustment write is planned for the skipped location. The parsed records and notification/PDF totals remain intact. Warnings propagate to console previews, run JSON and email content; these planning omissions are not included in the apply-stage `skipped_count`. The classification helper itself remains strict and still raises if called directly with an unknown ID.

`_resolve_existing_workbook_path` tries exact path, a unique punctuation/spacing-normalized stem match, then the highest `SequenceMatcher` score at least **0.92**, warning when a fallback is used. Searches are nonrecursive in the expected parent and exclude `~$` Excel temporary files. Fuzzy matching does not enforce a unique best score or independent supplier/location identity check. Review every fallback before original writes.

Month sheets are normalized against candidates such as `JUN 2026` and `JUNE 2026`, with month aliases in `config/excel_mapping.py`. Missing workbooks or month sheets warn and skip; the writer does not create settlement workbooks, monthly sheets, or date rows.

The header scanner examines at most the first **10 rows** for Date, Gross AMT, NET AMT and CC Fee on the same row. Normalization uppercases and collapses punctuation/spacing. Optional headers use `_get_header_column` and Pay+ aliases. Required-header detection does not perform a generic fuzzy column search.

Date row lookup first checks cached cell values, then evaluates simple same-date-column formulas such as `=$A$5+1` recursively, then infers dates from nearest real/cached anchor plus row distance. Supported direct values include dates/datetimes, Excel serials, and several ISO/US/named-month string forms. Nearest-anchor fallback assumes one calendar day per row and does not warn that it inferred the target. Blank/formula rows with intervening non-day rows require careful review.

## Financial mapping

| Parsed source | Planned destination and apply behavior |
| --- | --- |
| Latest CITGO/SUNOCO daily date | SET `Gross AMT` and `NET AMT`; ordinary fee cell is not written |
| Older CITGO/SUNOCO daily dates in the same report | Add gross/net as formulas; source `backdated_daily_total` |
| Every VALERO daily date | SET gross/net, including heuristic-promoted late full settlements |
| VALERO aggregated mobile adjustments | Add gross/net to existing values/formulas; SET net amount in `MOBILE PAY ADDED TO GROSS/NET` |
| VALERO dealer Pay+ summary | SET informational `VP+` column only; aliases include `VALERO PAY +`; no gross/net change |
| VALERO wholesaler Pay+ summary | Add same signed amount to gross/net; SET `VALERO PAY + ADDED TO GROSS/NET` |
| VALERO dealer monthly charge summary | SET positive `Monthly Val chgs in Fees`; augment `CC Fee` formula or numeric value; leave gross/net unchanged |
| VALERO wholesaler monthly charge summary | SET negative `Monthly Val chgs in Fees`; add that negative cell to `NET AMT`; leave gross and the CC Fee formula unchanged |
| SUNOCO discounts | No planned Excel value; shown in other outputs |
| Unclassified adjustments | No Excel write; retained for anomaly/notification review |

`_get_primary_daily_total_dates` chooses the latest daily date **across the report**, not separately per location, for non-VALERO suppliers. Therefore an older location/date is additive even if that is the only record for that location.

Mobile/Pay+/monthly summaries group by supplier, location ID, name and date. `build_excel_write_plan` warns if non-VALERO reports contain VALERO-specific adjustment lists. Planning modes are strings; enum/config declarations do not comprehensively enforce all writer behavior.

## Write order and rerun safeguards

Within each workbook the order is ordinary SET values (including dealer Pay+), backdated daily adds, mobile groups, monthly groups, then wholesaler Pay+ groups, followed by `wb.save`.

- **SET:** overwrite existing non-formula values, including different nonempty amounts. Existing formulas are skipped with warnings when `overwrite_formulas=False` (the default). Equality is not checked before recording a write.
- **Backdated daily:** `_build_additive_formula` preserves the visible arithmetic, e.g. numeric base plus signed amount, or appends to an existing formula; blank is treated as zero. Non-numeric non-formula text warns/skips. `_SETTLEMENT_AUTOMATION_LOG` is a hidden worksheet with operation ID, supplier/location/date, field, source and amount. Matching logged operations skip. The ID does not include report date, raw hash or report identity; equal-valued operations from distinct reports can be conflated, and a corrected amount becomes a new addition.
- **Mobile:** gross/net/mobile marker must all resolve or the group warns with no changes. If the marker net equals planned net within 0.01, skip adding again. A different nonzero numeric marker warns/skips the group. Otherwise append formulas and set the marker. Marker equality alone does not prove gross/net still include the adjustment, and does not compare gross/fees.
- **Wholesaler Pay+:** analogous marker/equality/mismatch logic with one Pay+ amount and gross/net formula additions. Dealer Pay+ uses ordinary SET logic.
- **Monthly:** classification comes from `config/locations.py` through `get_valero_location_type`. Require monthly/fee cells for dealers or monthly/net cells for wholesalers; incomplete groups are skipped. Dealers retain the positive monthly marker and fee adjustment. Wholesalers write a negative monthly marker and link NET to it with `=(existing net formula or numeric base)+monthly_cell`; blank NET uses zero, supporting locations with billing but no daily settlement. Gross and the CC Fee formula are not changed by the wholesaler monthly branch. Existing monthly-cell references are retained on rerun, so changing the negative monthly amount updates NET without a second deduction. Reference matching recognizes whole cell references and absolute variants (H4 is not H40), but is not a full Excel formula parser. Non-numeric/non-formula NET skips the whole group. Dealer numeric fallback still skips addition when the old monthly marker equals the new amount; otherwise it adds the full new charge, not the difference. Invalid dealer fee text still warns/skips that fee after the monthly cell changes.

Monthly billing dates still come from the parser (maximum expected settlement date); this change does not infer a date from handwritten corrections or reprocess historical workbooks. The workbook header remains `MONTHLY VAL CHGS IN FEES` for both classes. Parsed charges and email/PDF monthly summaries remain positive charge magnitudes; the class-specific sign is applied only when writing Excel.

Default formula protection applies to ordinary SET, not to intentional additive/monthly branches. These safeguards are operation-specific; rerunning arbitrary historical data is not universally idempotent. Do not clear cells or automation logs blindly to force a rerun.

## Fee checks and formulas

Plan fee validation compares `gross - net` with parsed fees at tolerance **0.02**; mismatches add warnings. This differs from report validation's 0.01 tolerance. Resolution records whether the CC Fee cell starts with `=`; a non-formula fee warns but does not block all writes. Formula content and calculated results are not validated against report totals.

The separate `scripts/create_settlement_workbooks.py` generates twelve month sheets with headers on row 2, literal dates on rows `day + 2`, totals, formatting and formulas. Its CC Fee formulas are `gross - net` for CITGO/VALERO, but `net - gross` for SUNOCO. Thus SUNOCO generated workbook fees are negative while normalized parser fees are positive. DIFF is gross-minus-store for CITGO/SUNOCO dealer, store-minus-gross for VALERO; SUNOCO wholesaler has no DIFF column. These are current template choices, not a reconciliation guarantee.

The generator's naming appends supplier when absent; the writer's naming does not. It also generates one VALERO schema with `VALERO PAY +`, while wholesaler writing expects an added-to-gross/net header. Generated files are not guaranteed to be drop-in matches for all writer targets. See [KNOWN_ISSUES](KNOWN_ISSUES.md).

openpyxl preserves/writes formulas but does not recalculate them. The writer's small evaluator only resolves date formulas. Excel or another compatible calculation engine is needed to verify resulting calculated display values; no such process is launched by the application. No tracked workbook fixture establishes current external formulas/layouts.

## Copies, backups, persistence, and locking

Default workbook root is `data/excel_workbooks`; default output root is `output/excel` (environment overrides are supported). Copy mode refreshes `{output-root}/{parsed-report-date}/{original-name}` from the original on every call, replacing an existing output copy. It does not accumulate across calls into that previous copy automatically.

Original mode defaults to a first backup at `{output-root}/_backups/{parsed-report-date}/{original-name}`. It copies only if that backup is absent. A rerun does not create a new version, and no restore is automatic. This differs from the clearing tool's timestamped `_clear_backups` and the historical repair staging backups.

Dry-run builds and resolves a plan and can read workbooks, but returns before copies, backups, cell writes or saves. It reports zero applied writes; it does not simulate all apply-time marker/formula decisions. Warnings are accumulated and can be repeated across resolution/apply summaries.

Workbook read/open errors are often converted to warnings and skipped. Copy/backup and save errors propagate to the caller; daily processing records an Excel error. There is no workbook-specific retry, file-lock workaround, transactional all-workbook save, atomic replacement or rollback. Earlier workbooks may already be saved when a later one fails. Counts lost with an exception cannot fully describe those partial writes.

Both daily pipeline services retain the Excel exception message in `RunError.message` (and therefore run JSON and notification content), print its traceback, and save an `excel_write` diagnostic under `output/diagnostics/{supplier}/{parsed-report-date}/`. The diagnostic includes the traceback, workbook/output roots and write flags. A diagnostic-save failure is printed without replacing the original Excel exception. Calling a pipeline service directly does not itself save a daily-run JSON; the caller must use `write_daily_run_artifact`, as the daily runner scripts do.

Verification on 2026-10-05 used the current application flow with a saved July 20 Monday report, temporary workbook copies and notification previews. All 78 Friday/Saturday/Sunday daily rows were written (223 cell changes across 26 locations). A synthetic combination with 51 monthly rows wrote 277 changes across all 27 configured locations; reopened gross/net and adjustment cells matched independent signed totals. Unknown monthly-location failures retained the original `ValueError`, location ID, traceback and error text in diagnostics, run JSON and notification previews in both daily services. Diagnostic-save failure also preserved the original error. All 41 source workbook hashes stayed unchanged. No live fetch/email, office workbook writes, deprecated-suite acceptance or October 5 source-report verification was performed.

The subsequently supplied October 5 raw report reproduced the production failure: monthly billing for location `30497` (Trust Way Valero, $140.40) raised an unknown-classification `ValueError` during planning, before workbook writes. The user confirmed it is a wholesaler with workbook `2026 CC TRUST WAY VALERO.xlsx`; it is now mapped in `VALERO_WHOLESALER_LOCATIONS`. An isolated replay of that actual report completed 301 cell writes across 28 template workbooks, including all 78 daily rows for October 2–4 and all 51 monthly records. Trust Way's October 4 monthly cell is -140.40 and NET references it from zero; gross remains blank. All 299 previously configured planned writes were unchanged, and reopened gross/net and adjustment cells matched independent totals. Notification previews/PDFs and run JSON were generated without sending email. The office workbook itself was not available for layout verification; source workbook hashes remained unchanged.

The subsequent location-isolation change preserved write plans for all 86 available reports with configured locations. Replaying October 5 with Trust Way temporarily unconfigured completed 299 writes across the other 27 workbooks with one warning, in both full and local daily services. Removing one dealer and one wholesaler completed 283 writes across 26 workbooks with two warnings. Reopened workbook values and formulas matched the fully configured baseline for every remaining location. With all 28 locations unconfigured, no workbook was written and the run had warning status with 28 warnings. Parsed data remained identical, warnings appeared in console/run JSON/plain-text and HTML previews, PDFs were generated, and all source workbook hashes stayed unchanged. These checks used isolated copies and the normal application services, without live fetching, email delivery or the deprecated suite.

`RunLock` protects daily runners that share `output/locks/daily_pipeline.lock`, not Excel files themselves and not all probes/repair scripts. Existing lock-file content is not proof that a process still holds the OS lock. Close external Excel editors for authorized writes and avoid concurrent writer tools; verify permissions and backup destinations before recovery.

## Reading success correctly

Missing targets, skipped formulas, differing markers and other warnings do not necessarily set `summary.has_errors` or cause exit 1. `written_count` counts status `written`; `skipped_count` counts change statuses starting `skipped`. Missing targets and incomplete groups can have warnings with **no** skipped-change entry. Inspect the printed plan, actual cell changes, expected workbooks and warnings, not only exit code or counts. Production layout, fuzzy match appropriateness and rerun accounting remain **Needs verification**.
