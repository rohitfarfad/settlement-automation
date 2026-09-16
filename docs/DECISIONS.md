# Current implementation choices

These entries document observable choices, not invented historical motivations. They are not approvals to redesign the system. Where source comments state intent, that is identified explicitly. Changes to financial behavior require scoped explanation and regression evidence.

## Supplier-specific parsing behind one entry point

**Current implementation:** `services/report_processor.py::parse_report` uses content detectors in `parser_registry.py` and calls separate CITGO, VALERO and SUNOCO functions. No parser inheritance layer is implemented; `parsers/base.py` is empty.

Each supplier extracts and normalizes its own format into `models.py::ParsedReport`. Shared dataclasses let validation, Excel and notifications consume consistent fields without erasing supplier-specific adjustment collections. Historical reasons for choosing this layout are not recorded. Future changes should retain understandable supplier-specific handling unless a smaller, clearly justified change requires otherwise.

## Fetching is separate from parsing

**Current implementation:** connectors return temporary file paths; `DownloadManager` stores raw input; only then does the daily service parse. Connector docstrings explicitly state that they do not parse, reconcile or write Excel. Content markers in fetch selection reject wrong reports, but do not replace parser dispatch or validation.

This exposes a raw-file boundary for local inspection/replay. The current deterministic raw path overwrites reruns; it is not an immutable audit store. Changing this requires an explicit storage/retention decision.

## Shared DTN sessions apply within a same-date call

**Current implementation:** `ingestion/dtn_group_fetch.py` loads one set of shared DTN credentials and handles selected DTN suppliers in one browser session. Its comments identify shared login as the intent and fast missing-report detection as useful for ranges/weekends.

The scheduled batch splits CITGO/SUNOCO and VALERO by requested date, so those two DTN suppliers use different sessions there. Do not document a single-login whole batch unless implementation changes.

## Report date is distinct from transaction and run dates

**Current implementation:** scripts choose a requested report date; supplier content supplies `ParsedReport.report_date`; normalized rows carry workbook transaction dates. `DailyRunSummary.business_date` remains a compatibility alias. SUNOCO's active fetch helper explicitly documents returning the caller's report date unchanged because the parser subtracts a day.

Batch defaults are yesterday for CITGO/SUNOCO and today for VALERO. The code does not establish the business rationale for those defaults or a holiday calendar. Date names alone are not reliable evidence in older APIs/config strings.

## VALERO uses structural classification before extraction

**Current implementation:** expected report dates and per-location block statistics identify daily settlements; other detail dates become mobile adjustments. Comments explicitly describe distinguishing a complete late store settlement from a small prior mobile-only block.

Pay+ is recognized by offer-row syntax rather than a restrictive card-code list; a code comment notes valid VISA rows. Monthly billing amounts are stored positive for adding into CC Fee. See [PARSER_GUIDE](PARSER_GUIDE.md) for exact thresholds, signs and boundaries. These implemented choices are not a guarantee of coverage for every real report.

## Workbook writes are planned and resolved before application

**Current implementation:** `services/excel_writer.py` separates planned values, actual workbook/cell resolution and applied changes. Dry-run exits before copies/backups/writes, while still resolving existing workbooks. The default public API is dry-run and non-original output, but the scheduled wrapper explicitly requests originals.

Ordinary gross/net writes leave CC Fee formulas in place. Special adjustments use explicit formulas/marker columns; the additive helper's docstring calls out visible arithmetic. Backdated daily entries additionally use a workbook-local hidden operation log. These are partial rerun protections, not a general transaction ledger.

## Office location maps determine workbook identity

**Current implementation:** `config/excel_mapping.py` prioritizes overrides and `config/locations.py` names over parser names. Its comments explicitly direct the caller not to strip supplier text or prefer report names over the office map. VALERO dealer/wholesaler membership controls whether Pay+ affects gross/net or only an informational column.

These maps are financial routing configuration, not cosmetic display names. The separate workbook generator is not fully aligned with writer naming/headers; see [KNOWN_ISSUES](KNOWN_ISSUES.md).

## Handled failures are aggregated, not globally fatal

**Current implementation:** the full daily service records fetch/parse/validation/Excel errors per result and continues where possible. A source comment calls validation errors blocking for that report's Excel write. Group-level fetch exceptions are converted to errors so the rest of a daily invocation can continue.

Excel resolution warnings allow remaining resolved cells to be applied. Summary anomalies are detected after writing and are advisory. The legacy local service has weaker gating. Do not generalize full-flow guarantees to every tool.

## Notifications are configured separately from Excel

**Current implementation:** `--notify` requests notification processing; enabled/mode settings decide off, preview, test send or live send. Test mode sends to configured test recipients and strips CC/BCC. Both single and batch flows attach generated supplier PDF summaries; they do not attach workbooks or raw portal files.

ReportLab creates PDFs directly from normalized reports. Graph client-credential HTTP submission is the only implemented sender. Combined batch notification runs after both per-run JSON files have been written. The repository does not explain the historical ordering decision or prove mailbox delivery.

## Minimal code is the permanent development policy

The requested repository policy is recorded in [AGENTS.md](../AGENTS.md): prefer the smallest correct implementation, minimal diffs, existing helpers and explicit logic; preserve behavior outside scope. Do not add speculative abstractions or dependencies. Financial correctness and traceability outrank architectural elegance. This is a development instruction for future work, distinct from inferred historical design choices.

All abbreviated module paths above are under `src/settlement_automation/` unless prefixed with `config/`. For full connections and operational limits, see [ARCHITECTURE](ARCHITECTURE.md), [DATA_FLOW](DATA_FLOW.md), and [OPERATIONS_RUNBOOK](OPERATIONS_RUNBOOK.md).
