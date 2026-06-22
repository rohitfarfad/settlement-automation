from _path_setup import PROJECT_ROOT  # noqa: F401

import argparse
from datetime import date, timedelta
from pprint import pprint

from config.settings import get_settings
from config.supplier_accounts import get_supplier_account
from settlement_automation.connectors.download_manager import DownloadManager
from settlement_automation.ingestion.fetch_reports import fetch_reports_for_account
from settlement_automation.services.diagnostics import (
    DiagnosticRecord,
    write_diagnostic_record,
    write_exception_diagnostic,
)
from settlement_automation.services.report_processor import parse_report
from settlement_automation.services.validation import validate_report
from settlement_automation.utils.env import load_local_env


def parse_business_date(value: str) -> date:
    return date.fromisoformat(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch a supplier report and test parser compatibility."
    )

    parser.add_argument(
        "--supplier",
        required=True,
        choices=["citgo", "valero", "sunoco"],
    )

    parser.add_argument(
        "--business-date",
        type=parse_business_date,
        default=date.today() - timedelta(days=1),
    )

    return parser


def diagnostics_dir(settings, supplier_name: str, business_date: date) -> str:
    return str(settings.output_dir / "diagnostics" / supplier_name / str(business_date))


def issue_to_dict(issue) -> dict:
    return {
        "level": getattr(issue, "level", "UNKNOWN"),
        "message": getattr(issue, "message", str(issue)),
    }


def main() -> int:
    args = build_parser().parse_args()

    settings = get_settings()
    load_local_env(settings.project_root)

    account = get_supplier_account(args.supplier)
    manager = DownloadManager(settings=settings)

    print(
        f"[STEP] Fetching supplier={account.supplier_name}, "
        f"business_date={args.business_date}"
    )

    fetch_result = fetch_reports_for_account(
        account=account,
        business_date=args.business_date,
        download_manager=manager,
        remove_downloaded_files=True,
        raise_on_error=False,
    )

    if not fetch_result.succeeded:
        print(f"[FAILED] Fetch failed: {fetch_result.error_message}")
        print(
            "[INFO] Check diagnostics under: "
            f"{diagnostics_dir(settings, account.supplier_name, args.business_date)}"
        )
        return 1

    print(f"[SUCCESS] Fetch completed. stored_reports={len(fetch_result.stored_reports)}")

    overall_success = True

    for stored_report in fetch_result.stored_reports:
        raw_path = stored_report.raw_path

        print("\n========== RAW REPORT ==========")
        print(f"raw_path={raw_path}")
        print(f"hash={stored_report.file_hash}")
        print(f"size_bytes={stored_report.size_bytes}")

        print("\n[STEP] Parsing raw report through official parser pipeline...")

        try:
            report = parse_report(str(raw_path))
        except Exception as exc:
            diagnostic_path = write_exception_diagnostic(
                account=account,
                business_date=args.business_date,
                step_name="parse_report_failed",
                exc=exc,
                settings=settings,
                page=None,
                artifact_paths=None,
                extra={
                    "raw_path": str(raw_path),
                    "file_hash": stored_report.file_hash,
                    "size_bytes": stored_report.size_bytes,
                },
            )

            print(f"[FAILED] parse_report failed for raw_path={raw_path}")
            print(f"[ERROR] {exc}")
            print(f"[DIAGNOSTIC] {diagnostic_path}")
            return 1

        print("[SUCCESS] parse_report completed.")

        print("\n[STEP] Validating parsed report...")

        try:
            validation_result = validate_report(report)
        except Exception as exc:
            diagnostic_path = write_exception_diagnostic(
                account=account,
                business_date=args.business_date,
                step_name="validate_report_failed",
                exc=exc,
                settings=settings,
                page=None,
                artifact_paths=None,
                extra={
                    "raw_path": str(raw_path),
                    "file_hash": stored_report.file_hash,
                    "size_bytes": stored_report.size_bytes,
                    "report_supplier": getattr(report, "supplier", None),
                    "report_date": str(getattr(report, "report_date", "")),
                },
            )

            print(f"[FAILED] validate_report failed for raw_path={raw_path}")
            print(f"[ERROR] {exc}")
            print(f"[DIAGNOSTIC] {diagnostic_path}")
            return 1

        print("[SUCCESS] validate_report completed.")

        print("\n========== PARSED DAILY TOTALS ==========")
        pprint(getattr(report, "daily_totals", None))

        print("\n========== MOBILE ADJUSTMENTS ==========")
        pprint(getattr(report, "mobile_adjustments", None))

        print("\n========== VALIDATION ==========")
        print(f"is_valid={validation_result.is_valid}")
        pprint(validation_result.issues)

        if not validation_result.is_valid:
            overall_success = False

            diagnostic_path = write_diagnostic_record(
                DiagnosticRecord(
                    supplier_name=account.supplier_name,
                    portal_name=account.portal_name,
                    business_date=str(args.business_date),
                    step_name="validation_failed",
                    status="failed",
                    message="validate_report returned is_valid=False",
                    extra={
                        "raw_path": str(raw_path),
                        "file_hash": stored_report.file_hash,
                        "size_bytes": stored_report.size_bytes,
                        "report_supplier": getattr(report, "supplier", None),
                        "report_date": str(getattr(report, "report_date", "")),
                        "daily_totals_count": len(getattr(report, "daily_totals", []) or []),
                        "mobile_adjustments_count": len(
                            getattr(report, "mobile_adjustments", []) or []
                        ),
                        "validation_issues": [
                            issue_to_dict(issue)
                            for issue in validation_result.issues
                        ],
                    },
                ),
                settings=settings,
            )

            print(f"[DIAGNOSTIC] {diagnostic_path}")

    if overall_success:
        print("\n[SUCCESS] Fetch, parse, and validation completed successfully.")
        return 0

    print("\n[FAILED] Fetch and parse completed, but validation failed.")
    print(
        "[INFO] Check diagnostics under: "
        f"{diagnostics_dir(settings, account.supplier_name, args.business_date)}"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())