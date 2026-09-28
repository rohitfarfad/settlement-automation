# Known issues and verification limits

This is an evidence-based audit, not a proposed redesign or a list of hypothetical defects. No application fixes were made. “Confirmed issue” means the mismatch or behavior is visible in current code/tests; it does not establish how often production encounters it. Business intent remains separate from implementation.

## Confirmed issues and mismatches

| Finding | Evidence and impact |
| --- | --- |
| Existing tests are not green | Audit run: 68 passed, 10 failed. Raw storage layout, email wording, SUNOCO date helper, and VALERO sectionless adjustment assertions disagree with source. Exact tests are listed in [TESTING](TESTING.md) |
| Local parse/write/notify does not block invalid reports from Excel | `services/daily_pipeline.py::run_daily_parse_write_notify` writes any non-null parsed report even when validation produces errors; full `run_daily_fetch_parse_write_notify` explicitly skips those writes |
| Local date alias is nonfunctional | `scripts/run_daily_parse_write_notify.py` declares `--business-date` but unconditionally calls `date.fromisoformat(args.report_date)`. Alias-only or omitted report date fails; both options are optional in argparse |
| Local script exit status does not reflect summary failures | The same script's `main()` prints results and returns None without an error-based `sys.exit`; missing reports can be printed as errors with process exit 0 |
| SUNOCO rule metadata is stale | `config/sunoco_reports.py` says business-date-plus-one, while `connectors/sunoco_date.py` returns the supplied report date; both date tests still expect +1 |
| Workbook generator and writer disagree on names | `create_settlement_workbooks.py::build_workbook_filename` appends supplier when absent; `config/excel_mapping.py::get_workbook_filename` uses office name as-is. For VALERO location 24640 mapped to CARMEL, creation yields `2026 CC CARMEL VALERO.xlsx`, writer expects `2026 CC CARMEL.xlsx`; fuzzy resolution is not a reliable compatibility guarantee |
| Generator lacks wholesaler-specific VALERO Pay+ header | It creates one VALERO schema with `VALERO PAY +`. `_append_valero_pay_plus_values` expects `VALERO PAY + ADDED TO GROSS/NET` for wholesalers; unresolved header produces an incomplete/skipped group. No generator/writer integration tests cover it |
| Exception base classes are redefined | `src/settlement_automation/exceptions.py` defines `SettlementAutomationError`, `ConfigurationError`, and `BrowserAutomationError` twice. Earlier `MissingCredentialsError` / `PortalDownloadError` inherit earlier class objects, so they are not subclasses of the final exported bases with those names. Broad Exception catches often still handle them, but typed hierarchy assumptions are wrong |
| Batch send outcome is absent from run JSON | `scripts/run_daily_batch.py` writes each artifact before calling `handle_daily_batch_notification`. Both child calls use `notify=False`, so neither JSON captures final combined mail success/failure. `latest.json` is only the second run |
| Batch PDF paths are dropped from returned result | `services/daily_batch_notification.py` collects and attaches PDF paths but omits `pdf_attachment_paths` in its returned `NotificationResult`. PDFs can exist/send despite no returned path list |
| Some configured controls are unused | `max_retries`, `download_timeout_seconds`, `excel_audit_dir` are loaded but not consumed by active fetch/writer flow. Empty retry/state modules do not provide those capabilities |
| Environment load order differs across tools | Some fetch/probe scripts construct settings before loading `.env`; batch loads first. Existing settings objects do not update, while credentials/portal settings read later can. See [CONFIGURATION](CONFIGURATION.md) |
| Clearing does not reset additive operation history | `scripts/clear_excel_entries.py` clears date-row cells but does not remove `_SETTLEMENT_AUTOMATION_LOG` entries. Replaying a cleared backdated operation can then skip as already logged |
| Declared package dependencies are insufficient for daily imports | `pyproject.toml` omits ReportLab; daily services import it through notifications/PDF module even without `--notify`. It is present in `requirements.txt`, so install path matters |

Relative `services/` and `connectors/` paths above are under `src/settlement_automation/`.

## Operational limitations

- **Raw files are replaceable, not versioned.** `DownloadManager` deletes the same supplier/date/suffix destination then copies/moves the new input. A hash is computed but does not deduplicate or preserve history. Multiple same-suffix reports for one supplier/date would target one path.
- **Excel writes are not transactional.** Missing/open/resolve conditions often warn and skip, while copy/save errors can propagate after earlier workbooks have been changed. No rollback or per-workbook lock/retry exists. Zero errors/exit 0 does not prove all planned cells were written.
- **Copy mode is per call, not cumulative.** Output copies are refreshed from originals at `{output}/{parsed-report-date}`; reruns replace existing copies. Original backups are only the first snapshot for a report date/name, not every attempt.
- **Idempotency is partial.** Backdated operation IDs omit report identity/hash; mobile markers compare only net, Pay+ markers only amount; dealer monthly numeric correction adds the full changed amount (wholesaler NET now references the negative monthly cell). Existing formula protection can also prevent a desired later SET. These limitations follow the writer branches, not an audited accounting policy.
- **No full-run retry/checkpoint state.** Browser waits/candidate attempts and manual rerun tools exist; `ingestion/retry_policy.py` and `state_store.py` are empty. Normalized records are not persisted to a database.
- **Notification is not an independent monitor.** A failure before summary/notify can prevent all email. Sender success means successful HTTP submission, not confirmed delivery. Repeated sends are not deduplicated. SMTP is unimplemented.
- **Limited control-total reconciliation.** SUNOCO now checks each location's daily net plus separate discount against `totalAdjustedNetAmount` in its parser. Validation also checks internal daily/mobile net arithmetic and duplicate daily keys. Supplier document grand totals and expected location completeness are not independently validated.
- **Diagnostic artifacts are not guaranteed or sanitized universally.** Many capture paths are best-effort. HTML/screenshots/traces and raw lines can contain confidential report/session data. Do not publish them unreviewed.
- **Historical repairs are high impact.** The dated PowerShell repair clears/copies original files; its CMD launcher can hard-reset Git. They are not routine retry tools. The repair's shared-root variable does not itself configure `run_daily.py`'s Excel environment.

## Fragile assumptions grounded in source

| Assumption | Source / consequence |
| --- | --- |
| Detection cleanup is enough for an input | `report_processor.py` dispatches on cleaned text but parsers reread original bytes; HTML wrappers can detect successfully and still lose extraction |
| Unmatched lines need no record | CITGO skips regex misses; VALERO keeps unknown adjustments only in the section and only for its five-digit/signed-row pattern. “Unclassified” does not mean all unknown input was captured |
| MMDD implies one safe year | CITGO always uses report year; VALERO moves any future MMDD into the prior year. Neither is a complete date reconciliation policy |
| VALERO block shape determines a late full day | Heuristic uses POS/CRIND presence, counts and non-mobile card variety. Thresholds and unusual/holiday reports lack representative regression coverage |
| SUNOCO missing sales/fee amounts mean zero | `to_decimal` still converts falsey sales/fee values to zero; adjustment, discount and adjusted-net fields are now required. Null location ID stringifies to a nonempty value, and blank names bypass literal UNKNOWN warnings |
| SUNOCO fixed UTC request window fits every date | `sunoco_api.py` uses 05:00Z to next-day 04:59:59.999Z without seasonal conversion; current portal convention is not established by offline code inspection |
| Nearest workbook filename is correct | `_resolve_existing_workbook_path` accepts best fuzzy score >=0.92 without requiring unambiguous best match |
| One row equals one date | `_infer_date_from_nearest_anchor` extrapolates by row distance without validating intervening row purpose |
| Formula reference substring means already linked | `_formula_references_cell` tests text containment, not parsed formula references; similarly-prefixed addresses can be mistaken for the intended cell |
| Notification totals equal workbook totals | Display total net adds all Pay+ while dealer Excel does not; display gross excludes Pay+, and monthly/discount categories stay separate. These outputs answer different implemented calculations |

## Coverage gaps

Dedicated CITGO, reconciliation and anomaly test files and both sample report files are empty. SUNOCO has no dedicated parser test. No automated full Excel writer/generator, daily/batch orchestrator, process lock, artifact writer, successful Graph send or live scheduler/portal test proves production behavior. PDF generation has only indirect execution, not content/layout verification. See [TESTING](TESTING.md) for the complete inventory.

## Needs verification

- Actual installed Windows scheduled task: executable/arguments, trigger time, account, overlap/retry policy and working environment. Repository wrapper intent is established; installed state is not.
- Production Python/dependency versions and a fresh install using all requirement pins on supported platforms.
- Active workbook root/share permissions, exact filenames/month headers, formulas, recalculation and completeness of location/type mapping.
- Real portal markup, authentication/MFA, date availability/retention, report completeness, SUNOCO timezone convention and VALERO holiday/late-block examples.
- Business approval of existing sign/date/classification choices, adjustment treatment and notification-total interpretation; the code establishes behavior, not its historical approval.
- Tenant/mailbox permissions, effective recipients, send/delivery and notification policy on the production host.
- Safe representative parser fixtures and production input/control totals. No real workbook or populated sample input is tracked to verify these claims against.

## README discrepancies

| Historical claim/reference | Current evidence |
| --- | --- |
| `README.md` treats SUNOCO connector, scheduler orchestration and notification as future work | SUNOCO browser/API connector, two-date batch, PowerShell wrapper, Graph notifications and PDFs exist |
| Both READMEs show raw portal/supplier/year/month/day storage and duplicate avoidance | Current `DownloadManager` uses supplier/year/month/deterministic filename and overwrites |
| `README_updated.md` says SUNOCO fetch adds one day | Active helper returns exact supplied report date; parser subtracts one for transaction rows |
| `README_updated.md` describes Excel writer as later work and old VALERO date assumptions | Implemented writer has plan/resolve/apply, dealer/wholesaler Pay+, monthly formulas and per-location late-day parsing |
| README commands reference `cli2.py`, `browser_download_smoke.py`, or probes directly under `scripts/` | First two files are absent; active parser CLI is `settlement_automation.cli`, four UI probes are under `scripts/probes/` |
| `state/report_runs.sqlite` appears as future structure | No current SQLite workflow; placeholder state module is empty; current results are JSON plus a process lock and workbook-local operation log |
| Audit exports should precede Excel | Actual daily pipeline does not call CSV exporter; parser CLI's `--export-csv` is separate |

The historical README files were intentionally left unchanged. New documentation is linked through root [AGENTS.md](../AGENTS.md) and grounded in current source.
