from _path_setup import PROJECT_ROOT  # noqa: F401

import argparse
from datetime import date, timedelta
from pathlib import Path

from config.portal_rules import get_dtn_portal_rule
from config.settings import get_settings
from config.supplier_accounts import get_supplier_account
from settlement_automation.connectors.browser import (
    capture_failure_artifacts,
    open_browser_session,
)
from settlement_automation.connectors.credentials import load_credentials
from settlement_automation.connectors.download_manager import DownloadManager
from settlement_automation.connectors.dtn_page import login_to_dtn
from settlement_automation.exceptions import (
    PortalDownloadError,
    PortalNavigationError,
)
from settlement_automation.ingestion.dtn_group_fetch import (
    capture_one_dtn_supplier_report_from_open_session,
)
from settlement_automation.services.console_output import section, status_line
from settlement_automation.services.diagnostics import write_exception_diagnostic
from settlement_automation.utils.env import load_local_env


DTN_SUPPLIERS = ("citgo", "valero")


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def iter_dates(start_date: date, end_date: date):
    current = start_date

    while current <= end_date:
        yield current
        current += timedelta(days=1)


def parse_suppliers(value: str) -> list[str]:
    normalized = value.strip().lower()

    if normalized in {"both", "dtn", "all"}:
        return ["citgo", "valero"]

    selected = []

    for part in normalized.split(","):
        supplier = part.strip().lower()

        if not supplier:
            continue

        if supplier not in DTN_SUPPLIERS:
            raise argparse.ArgumentTypeError(
                f"Unsupported DTN supplier '{supplier}'. "
                "Expected citgo, valero, citgo,valero, both, dtn, or all."
            )

        if supplier not in selected:
            selected.append(supplier)

    if not selected:
        raise argparse.ArgumentTypeError("At least one supplier must be selected.")

    return selected


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Probe DTN date-range download in one login/browser session. "
            "Missing reports are logged and skipped."
        )
    )

    parser.add_argument(
        "--start-date",
        required=True,
        type=parse_date,
        help="Start business date, inclusive. Format: YYYY-MM-DD.",
    )

    parser.add_argument(
        "--end-date",
        required=True,
        type=parse_date,
        help="End business date, inclusive. Format: YYYY-MM-DD.",
    )

    parser.add_argument(
        "--suppliers",
        type=parse_suppliers,
        default=["citgo", "valero"],
        help="citgo, valero, citgo,valero, both, dtn, or all. Default: both.",
    )

    parser.add_argument(
        "--skip-weekends",
        action="store_true",
        help="Skip Saturday/Sunday instead of logging NOT FOUND.",
    )

    parser.add_argument(
        "--record-trace",
        action="store_true",
        help="Record Playwright trace for the session.",
    )

    return parser


def is_missing_report_error(exc: Exception) -> bool:
    message = str(exc).lower()

    missing_markers = [
        "no dtn rows found",
        "no dtn report content matched",
        "could not find dtn date option",
        "target report row was not found",
    ]

    return isinstance(exc, (PortalDownloadError, PortalNavigationError)) or any(
        marker in message for marker in missing_markers
    )


def main() -> int:
    args = build_parser().parse_args()

    if args.end_date < args.start_date:
        raise SystemExit("--end-date must be >= --start-date")

    settings = get_settings()
    load_local_env(settings.project_root)

    portal_rule = get_dtn_portal_rule()
    download_manager = DownloadManager(settings=settings)

    # CITGO and Valero share DTN credentials, so use first supplier as session account.
    session_account = get_supplier_account(args.suppliers[0])
    credentials = load_credentials(session_account)

    section("DTN RANGE DOWNLOAD PROBE")
    status_line("Start Date", args.start_date)
    status_line("End Date", args.end_date)
    status_line("Suppliers", ", ".join(args.suppliers))
    status_line("Login URL", portal_rule.login_url)
    status_line("Single Session", "yes")

    results: list[dict] = []

    try:
        with open_browser_session(
            account=session_account,
            settings=settings,
            record_trace=args.record_trace,
        ) as session:
            page = session.page

            section("LOGIN")
            print("Logging into DTN once for the full date range...")

            login_to_dtn(
                page=page,
                login_url=portal_rule.login_url,
                username=credentials.username,
                password=credentials.password,
            )

            print("Login completed.")

            for business_date in iter_dates(args.start_date, args.end_date):
                if args.skip_weekends and business_date.weekday() >= 5:
                    section(f"DATE {business_date}")
                    print("SKIPPED: weekend")
                    for supplier in args.suppliers:
                        results.append(
                            {
                                "date": business_date,
                                "supplier": supplier,
                                "status": "SKIPPED_WEEKEND",
                                "raw_path": "",
                                "error": "",
                            }
                        )
                    continue

                section(f"DATE {business_date}")

                for supplier in args.suppliers:
                    account = get_supplier_account(supplier)

                    print(f"\n[{supplier.upper()}] Fetching report...")

                    try:
                        tmp_paths = capture_one_dtn_supplier_report_from_open_session(
                            page=page,
                            account=account,
                            business_date=business_date,
                            settings=settings,
                        )

                        stored_reports = []

                        for tmp_path in tmp_paths:
                            stored = download_manager.store_raw_report(
                                source_path=Path(tmp_path),
                                account=account,
                                business_date=business_date,
                                remove_source=True,
                            )
                            stored_reports.append(stored)

                        for stored in stored_reports:
                            print(f"[{supplier.upper()}] SAVED: {stored.raw_path}")
                            print(f"[{supplier.upper()}] HASH : {stored.file_hash}")

                            results.append(
                                {
                                    "date": business_date,
                                    "supplier": supplier,
                                    "status": "SAVED",
                                    "raw_path": str(stored.raw_path),
                                    "error": "",
                                }
                            )

                    except Exception as exc:
                        if is_missing_report_error(exc):
                            print(f"[{supplier.upper()}] NOT FOUND: {exc}")

                            results.append(
                                {
                                    "date": business_date,
                                    "supplier": supplier,
                                    "status": "NOT_FOUND",
                                    "raw_path": "",
                                    "error": str(exc),
                                }
                            )
                            continue

                        print(f"[{supplier.upper()}] FAILED: {exc}")

                        artifacts = {}
                        try:
                            artifacts = capture_failure_artifacts(
                                page=page,
                                settings=settings,
                                account=account,
                                step_name="dtn_range_download_failed",
                            )
                        except Exception:
                            pass

                        try:
                            diagnostic_path = write_exception_diagnostic(
                                account=account,
                                business_date=business_date,
                                step_name="dtn_range_download_failed",
                                exc=exc,
                                settings=settings,
                                page=page,
                                artifact_paths=artifacts,
                                extra={
                                    "start_date": str(args.start_date),
                                    "end_date": str(args.end_date),
                                    "suppliers": args.suppliers,
                                },
                            )
                            print(f"[{supplier.upper()}] DIAGNOSTIC: {diagnostic_path}")
                        except Exception:
                            diagnostic_path = ""

                        results.append(
                            {
                                "date": business_date,
                                "supplier": supplier,
                                "status": "FAILED",
                                "raw_path": "",
                                "error": str(exc),
                            }
                        )

                        # Keep going even on unexpected supplier/date failure.
                        continue

    except Exception as exc:
        section("SESSION FAILED")
        print(f"DTN range session failed before completion: {exc}")
        return 1

    section("RANGE DOWNLOAD SUMMARY")
    print(f"{'Date':<12} {'Supplier':<10} {'Status':<18} {'Raw Path'}")
    print("-" * 100)

    for row in results:
        print(
            f"{str(row['date']):<12} "
            f"{row['supplier']:<10} "
            f"{row['status']:<18} "
            f"{row['raw_path']}"
        )

    print("-" * 100)

    failed_count = sum(1 for row in results if row["status"] == "FAILED")
    saved_count = sum(1 for row in results if row["status"] == "SAVED")
    not_found_count = sum(1 for row in results if row["status"] == "NOT_FOUND")
    skipped_count = sum(1 for row in results if row["status"] == "SKIPPED_WEEKEND")

    status_line("Saved", saved_count)
    status_line("Not Found", not_found_count)
    status_line("Skipped Weekend", skipped_count)
    status_line("Failed", failed_count)

    # Missing reports are acceptable. Unexpected failures make exit code 1.
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())