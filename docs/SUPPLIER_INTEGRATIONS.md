# Supplier integrations

`config/supplier_accounts.py` defines three active accounts. `src/settlement_automation/connectors/__init__.py::get_connector` routes by portal; `ingestion/supplier_selection.py` supports individual names, comma-separated lists, `dtn`, and `all`, normalizes case, and deduplicates CLI selections.

## Shared fetch contract

`SupplierPortalConnector.fetch_reports(business_date)` returns temporary paths without parsing. The daily caller passes its requested report date into that legacy argument. `ingestion/fetch_reports.py::fetch_reports_for_account` invokes the connector and `DownloadManager`, returning `FetchResult(status='success'|'failed')`. Exceptions normally become error text; `raise_on_error=True` is available at API level. It can report success with no stored paths, which the daily pipeline separately rejects.

`connectors/browser.py::open_browser_session` launches Playwright Chromium with a fresh context and `accept_downloads=True`. Browser downloads are rooted at `data/tmp/browser/{portal}/{supplier}`; current captures explicitly save text at the paths below. Full daily connectors request tracing, written under `output/traces/{supplier}/`. Context/browser close in `finally`; there is no persistent authenticated profile or MFA flow implemented.

Credential values are loaded externally via `load_credentials`, stripped and checked for emptiness. `PortalCredentials.password` is excluded from repr, but usernames and sensitive data in other objects/traces are not comprehensively redacted. Do not print or publish them.

`DownloadManager.store_raw_report` stores `data/raw/{supplier}/YYYY/MM/{supplier}_{requested-date}{suffix}`. Source suffix is retained (default `.txt` if absent); all current live connectors save `.txt`. It computes SHA-256/size and copies or moves, deleting an existing destination first. Daily fetching moves temporary files. There is no skip-existing, hash-based deduplication, atomic replacement, or raw-file version history.

`MAX_RETRIES` and `DOWNLOAD_TIMEOUT_SECONDS` are loaded settings but not used by the current connector paths. Polling, selector fallbacks and trying alternate DTN candidate rows are implemented; a configurable whole-fetch retry/backoff policy is not. Connector navigation/API timeouts are commonly hardcoded to 60 seconds.

## CITGO through DTN

| Aspect | Current behavior |
| --- | --- |
| Portal/source | DTN Fuel Buyer (`fuelbuyer.dtn.com/energy`), DataConnect message list |
| Configuration | `DTN_USERNAME`, `DTN_PASSWORD`, `DTN_LOGIN_URL`, `DTN_DATACONNECT_URL`; `config/dtn_reports.py::DTN_REPORT_TARGETS['citgo']` |
| Target row | Report name `Citgo Petroleum`, group `Credit Card`, document `Credit Card Memo` |
| Content selection | Require `CITGO DAILY RECEIVED TRANSACTION SUMMARY`; reject `PREPAID CARD ACTIVATIONS` |
| Capture | Click candidate row in same page; read longest visible text across pre/textarea/report/message/body candidates; trim from configured start marker |
| Temporary path | `data/tmp/dtn/citgo/{date}/citgo_credit_card_memo_{date}_row_{n}.txt` |
| Raw path | `data/raw/citgo/YYYY/MM/citgo_{date}.txt` |
| Parser | `parsers/citgo_parser.py::parse_citgo_report` via content registry |
| Processing/output | Group unsigned detail amounts by location/date; office names from location map; Excel latest date SET, older dates additive; daily/date-total email/PDF sections |
| Tests | Target/content/date/factory/fetch/storage tests; dedicated parser test and sample input are empty |

The DTN date dropdown accepts normalized padded/unpadded English labels and several numeric value formats (`connectors/dtn_date.py`). Row discovery searches increasingly broad table selectors, skips headers/empty/over-500-character layout rows, and deduplicates identical row text. Capture waits a fixed five seconds after clicking. It returns the **first content-accepted report**, not all matching documents or a largest-file choice.

No row or no accepted content raises a portal error. Strict date-option matching can reject unavailable historical dates. Authentication uses selector fallbacks and broad URL/text/password-field-disappearance signals, not proof that subsequent report content is correct.

## VALERO through DTN

| Aspect | Current behavior |
| --- | --- |
| Portal/config | Same DTN source and shared credential variable names as CITGO |
| Target row | `Valero R & M` / `Credit Card` / `Credit Card Memo` |
| Content selection | No required/rejected content markers configured; trim from `VALERO` start markers, then parser dispatch performs stricter detection |
| Temporary path | `data/tmp/dtn/valero/{date}/valero_credit_card_memo_{date}_row_{n}.txt` |
| Raw path | `data/raw/valero/YYYY/MM/valero_{date}.txt` |
| Parser/models | `parse_valero_report`; daily totals, mobile detail, Pay+, monthly charges, unclassified adjustments |
| Dates | Header report date; previous-day or Monday weekend expected dates; per-location complete-block heuristic can promote late dates; MMDD prior-year fallback |
| Excel | Daily SET; aggregate mobile adds to gross/net; dealer Pay+ informational only, wholesaler Pay+ additive; monthly charge cell plus CC Fee adjustment |
| Tests | Four synthetic parser cases (two failing); selection/date/storage/fetch tests. No late-full-day or workbook regression tests |

`ingestion/dtn_group_fetch.py::fetch_dtn_reports_for_supplier_group` logs in once for same-date DTN suppliers and reopens DataConnect for each candidate. It waits up to 15 seconds for a message list/empty state, then fails fast if no supplier rows exist. The standalone `DTNPortalConnector` instead waits up to 60 seconds for target rows. Per-supplier capture failures collect diagnostics and continue; login/session failure marks the requested group failed. Batch CITGO and VALERO use different calls/dates, so do not share one session there.

VALERO details and adjustment assumptions are described fully in [PARSER_GUIDE](PARSER_GUIDE.md). Unknown adjustment rows are retained only if they match the section-specific regex. Review warning output; unmatched content is not universally preserved.

## SUNOCO portal and OData API

| Aspect | Current behavior |
| --- | --- |
| Portal | `portal.sunocolp.com`, reports page `/financial/settlement` |
| Configuration | `SUNOCO_USERNAME`, `SUNOCO_PASSWORD`, `SUNOCO_LOGIN_URL`, `SUNOCO_REPORTS_URL` |
| API | Hardcoded `https://api.portal.sunocolp.com/odata/SettlementSummary` in `connectors/sunoco_api.py` |
| Authentication | Browser form login; intercept a real frontend SettlementSummary request and replay its auth headers through the authenticated context request client |
| Request date | Exactly the caller's requested report date; no +1 transformation in the active helper |
| Temporary path | `data/tmp/sunoco/{requested-date}/sunoco_settlement_{request-date}_business_{requested-date}.txt` |
| Raw path | `data/raw/sunoco/YYYY/MM/sunoco_{requested-date}.txt`, containing JSON |
| Parser | `parsers/sunoco_parser.py::parse_sunoco_report` |
| Output | Prior-day daily triples with inverted dealer fee/recomputed net; separate JSON `adjustments` discounts for reporting; Excel writes gross/net only |
| Tests | API URL/filter/header/pagination, capture marker/save and factory tests; date tests are stale; no dedicated parser tests |

The connector installs its request listener before login, opens the settlement page, and waits eight seconds for frontend requests. No captured headers raises `PortalDownloadError`. Replay drops transport headers (`host`, `content-length`, `connection`, `accept-encoding`) and supplies Accept/Origin/Referer defaults; auth is kept in memory, not documented as values.

The date filter uses a fixed UTC window from requested date at `05:00:00.000Z` through next day `04:59:59.999Z`. It expands location/business unit/header data, orders by settlement date descending and pages with `$skip`/`$top` (default 250). Pagination stops on empty values, reaching `@odata.count`, or a short page. Non-OK HTTP, invalid JSON, and non-list `value` fail; record dates and duplicate content are not verified here. Actual daylight-saving/portal date-window correctness is **Needs verification**.

Combined JSON preserves context/count or supplies defaults. `sunoco_capture.validate_sunoco_json_text` parses it and searches serialized JSON for configured markers; this is not a per-record schema validator. `save_sunoco_json_text` pretty-prints JSON to `.txt`. An empty settlement result usually lacks required row markers and fails capture rather than becoming a successful empty day.

`config/sunoco_reports.py.portal_request_date_rule` still says business-date-plus-one, but is not used to calculate the active request date. Source helper and parser semantics take precedence.

## Failures and evidence

Fetch failures can produce screenshots/HTML and `output/diagnostics/{supplier}/{requested-date}/{timestamp}_{step}.json`, with traceback and optional row/URL metadata. Session traces are separate. Diagnostic creation is often best-effort and not guaranteed for every early failure. Preserve raw inputs separately before a refetch because the destination is replaced.

All live portal markup, report availability/retention, MFA requirements, credentials and production access are **Needs verification**. The audit traced source and exercised offline tests; it did not authenticate to suppliers. See [OPERATIONS_RUNBOOK](OPERATIONS_RUNBOOK.md).
