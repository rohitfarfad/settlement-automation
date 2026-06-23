from _path_setup import PROJECT_ROOT  # noqa: F401

import argparse
from datetime import date, timedelta

from config.settings import get_settings
from config.supplier_accounts import get_supplier_account
from settlement_automation.connectors.download_manager import DownloadManager
from settlement_automation.ingestion.fetch_reports import fetch_reports_for_account
from settlement_automation.services.console_output import (
    print_daily_totals,
    print_final_status,
    print_mobile_adjustments,
    print_mobile_adjustment_summary,
    print_raw_file_info,
    print_report_summary,
    print_run_header,
    print_validation_result,
    section,
    status_line,
)
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

    print_run_header(
        title="FETCH AND PARSE PROBE",
        supplier=account.supplier_name,
        portal=account.portal_name,
        business_date=args.business_date,
    )

    section("FETCH")
    print("Starting supplier fetch...")

    fetch_result = fetch_reports_for_account(
        account=account,
        business_date=args.business_date,
        download_manager=manager,
        remove_downloaded_files=True,
        raise_on_error=False,
    )

    if not fetch_result.succeeded:
        diagnostics_path = diagnostics_dir(
            settings=settings,
            supplier_name=account.supplier_name,
            business_date=args.business_date,
        )

        print()
        print("FETCH FAILED")
        status_line("Error", fetch_result.error_message)
        status_line("Diagnostics", diagnostics_path)

        print_final_status(success=False, diagnostics_path=diagnostics_path)
        return 1

    print("Fetch completed successfully.")
    status_line("Stored Reports", len(fetch_result.stored_reports))

    overall_success = True
    last_diagnostic_path = None

    for index, stored_report in enumerate(fetch_result.stored_reports, start=1):
        raw_path = stored_report.raw_path

        section(f"STORED REPORT {index} OF {len(fetch_result.stored_reports)}")

        print_raw_file_info(
            raw_path=raw_path,
            file_hash=stored_report.file_hash,
            size_bytes=stored_report.size_bytes,
        )

        section("PARSE")
        print("Parsing raw report through official parser pipeline...")

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

            last_diagnostic_path = diagnostic_path
            overall_success = False

            print()
            print("PARSE FAILED")
            status_line("Raw Path", raw_path)
            status_line("Error", exc)
            status_line("Diagnostic", diagnostic_path)

            continue

        print("parse_report completed successfully.")

        section("VALIDATE")
        print("Validating parsed report...")

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

            last_diagnostic_path = diagnostic_path
            overall_success = False

            print()
            print("VALIDATION ERROR")
            status_line("Raw Path", raw_path)
            status_line("Error", exc)
            status_line("Diagnostic", diagnostic_path)

            continue

        print("validate_report completed successfully.")

        print_report_summary(report, raw_path=raw_path)
        print_daily_totals(report.daily_totals)
        print_mobile_adjustments(report.mobile_adjustments)
        print_mobile_adjustment_summary(report.mobile_adjustments)
        print_validation_result(validation_result)

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

            last_diagnostic_path = diagnostic_path
            status_line("Validation Diagnostic", diagnostic_path)

    print_final_status(
        success=overall_success,
        diagnostics_path=last_diagnostic_path,
    )

    return 0 if overall_success else 1


if __name__ == "__main__":
    raise SystemExit(main())