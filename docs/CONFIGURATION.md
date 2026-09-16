# Configuration and environment

## Runtime and dependencies

`pyproject.toml` declares Python **>=3.10**, setuptools/wheel, and project dependencies Playwright, python-dotenv, and openpyxl. `requirements.txt` additionally lists pytest, pandas/numpy and related packages, and unpinned ReportLab. Core daily imports require ReportLab through notification/PDF modules even when notifications are disabled; installing only project metadata does not supply it.

The declared minimum is not proof that every current requirement pin works on every Python >=3.10. Fresh installation across Python versions is **Needs verification**. The audit used the existing Python **3.12.6** environment without installing dependencies.

There is no console-script entry in project metadata. Packages are discovered under `src`; top-level `config/` is imported by application code. Use the repository root and `scripts/_path_setup.py`-based scripts, or set `PYTHONPATH` for module CLI/tests. Standalone wheel deployment is not established by this repository.

## Configuration sources and precedence

`config/settings.py::get_settings` constructs a fresh frozen `AppSettings` from process environment each time. `PROJECT_ROOT` comes from the config file location. There is no automatic dotenv load in `get_settings`.

`src/settlement_automation/utils/env.py::load_local_env` loads root `.env` if present and python-dotenv is importable, using **`override=True`**. A `.env` value therefore overrides an already-set shell variable when this helper runs. Do not assume `$env:NOTIFICATION_EMAIL_MODE = 'dry_run'` is sufficient for a runner that then loads a live `.env`.

| Caller | Environment behavior |
| --- | --- |
| `run_daily_batch.py`, `daily_batch.py` | Load `.env` before `get_settings` |
| `run_daily.py` | Reads settings, loads `.env`, then reads settings again before running |
| `fetch_only.py`, `fetch_and_parse_probe.py`, DTN range/browser probes | Generally construct settings before loading `.env`; objects already built keep their old settings, while later credentials/portal rules/settings can see new values |
| `run_daily_parse_write_notify.py`, `write_excel_probe.py`, `write_excel_range.py`, `send_test_notification_email.py`, parser CLI | Do not call the dotenv helper; use inherited process environment/defaults |
| PowerShell scheduled wrapper | Does not parse `.env`; child batch does |

`.env.example` enumerates settings but is not proof of runtime values. This audit inspected its variable names only. Never copy credentials, tokens or private recipients into documentation, examples, commits or diagnostics shared externally.

## Environment variables

Defaults below are from source, not an installed machine's configuration.

| Variable | Default / purpose |
| --- | --- |
| `DTN_USERNAME`, `DTN_PASSWORD` | Required for live CITGO/VALERO fetch; shared portal account |
| `SUNOCO_USERNAME`, `SUNOCO_PASSWORD` | Required for live SUNOCO fetch |
| `DTN_LOGIN_URL` | `https://fuelbuyer.dtn.com/energy` |
| `DTN_DATACONNECT_URL` | DTN `/energy/common/link.do?contentId=750701&parentId=-1` |
| `SUNOCO_LOGIN_URL` | `https://portal.sunocolp.com/` |
| `SUNOCO_REPORTS_URL` | `https://portal.sunocolp.com/financial/settlement` |
| `HEADLESS_BROWSER` | `true`; used by Chromium launch |
| `DOWNLOAD_TIMEOUT_SECONDS` | `60`; parsed but not consumed by current live connector timeout logic |
| `MAX_RETRIES` | `3`; parsed but no implemented fetch retry policy consumes it |
| `EXCEL_WORKBOOK_ROOT` | `{repository}/data/excel_workbooks` |
| `EXCEL_OUTPUT_DIR` | `{repository}/output/excel` |
| `EXCEL_AUDIT_DIR` | `{repository}/output/audit`; not used by the current daily writer/exporter |
| `NOTIFICATION_EMAIL_ENABLED` | `false`; master notification enable switch |
| `NOTIFICATION_EMAIL_MODE` | `off`; validated choices `off`, `dry_run`, `test`, `live` |
| `NOTIFICATION_EMAIL_PROVIDER` | `graph`; choices `graph`, `smtp`; SMTP send unimplemented |
| `NOTIFICATION_EMAIL_TO`, `NOTIFICATION_EMAIL_CC`, `NOTIFICATION_EMAIL_BCC` | Empty; live recipients, comma or semicolon separated |
| `NOTIFICATION_EMAIL_TEST_TO` | Empty; sole To list in test mode, with CC/BCC cleared |
| `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`, `GRAPH_SENDER_EMAIL` | Empty; required by Graph sender |

Boolean true tokens are `1,true,yes,y,on` ignoring case/whitespace; other supplied values are false. Blank/missing integer settings use defaults; malformed integers raise. Excel path values are passed to `Path` directly, without `_get_path` normalization: relative paths depend on current working directory, and `~` is not explicitly expanded. `_get_path` exists but is not used for those settings.

Use credential documentation such as `DTN_USERNAME=<configured externally>`, never a real value. Runtime Graph authentication posts client credentials for the `.default` scope and sends as the configured user via Graph. Tenant permissions, consent, mailbox access and actual recipient policy are **Needs verification**; no provisioning script proves them.

## Notification controls

`services/notifications.py::load_notification_config` validates mode/provider and forces mode off when disabled. Runners additionally require `--notify` to invoke their notification path.

| Effective mode | Preview/PDF | Send behavior |
| --- | --- | --- |
| Disabled or `off` | None | No send |
| Enabled `dry_run` | Text/HTML and supplier PDFs | No send |
| Enabled `test` | Text/HTML and supplier PDFs | Real Graph send to test To only |
| Enabled `live` | Text/HTML and supplier PDFs | Real Graph send to live To/CC/BCC |

`--excel-dry-run` is independent of notification mode. The PowerShell wrapper's `-ExcelDryRun` still requests notification unless `-NoNotify` is also supplied. No email deduplication/retry is implemented. `send_test_notification_email.py` honors configured mode, including `live`; its name is not a safeguard.

## Fixed paths and rule files

`get_settings` fixes `data/`, `data/raw/`, `data/tmp/`, `output/`, `output/logs/`, `output/traces/`, and `output/notifications/` under the repository. There are no raw-root or notification-output environment overrides in this implementation; individual tools may accept explicit path arguments or configuration objects.

| File | Controls |
| --- | --- |
| `config/supplier_accounts.py` | Accounts, active flags, portal routing, credential variable names, format/parser metadata |
| `config/portal_rules.py` | Environment-aware login/report URLs; SUNOCO API base remains hardcoded in connector module |
| `config/dtn_reports.py` | Row names and content markers |
| `config/sunoco_reports.py` | JSON markers and temporary suffix; date-rule string is stale and not used by active date helper |
| `config/supplier_rules.py` | VALERO mobile-code set; declared Pay+ set is not used to restrict matched offers |
| `config/locations.py` | Office workbook names and dealer/wholesaler groups; these are financially significant mappings |
| `config/excel_mapping.py` | Workbook overrides, monthly aliases, headers, tolerances and policy objects; some descriptive policy fields are not wired into all branches |

`ExcelWriterPolicy` declares missing-target policies and no sheet/date creation. Actual resolution warns/skips, and apply continues with resolved targets even if warnings exist. `save_to_copy_by_default` and several mobile policy fields should not be mistaken for complete behavior switches; execution is governed by writer branches and explicit arguments.

There are no separate development/production profiles or centralized logging-level controls. CLI flags, environment, explicit function settings and external workbook roots distinguish runs. For portable setup/invocation and safe previews, see [OPERATIONS_RUNBOOK](OPERATIONS_RUNBOOK.md).
