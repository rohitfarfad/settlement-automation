from _path_setup import PROJECT_ROOT  # noqa: F401

import argparse
from datetime import date, timedelta

from config.settings import get_settings
from config.supplier_accounts import get_supplier_account
from settlement_automation.connectors.download_manager import DownloadManager
from settlement_automation.ingestion.dtn_group_fetch import (
    fetch_dtn_reports_for_supplier_group,
)
from settlement_automation.ingestion.fetch_reports import fetch_reports_for_account
from settlement_automation.ingestion.supplier_selection import (
    SUPPORTED_SUPPLIERS,
    group_suppliers_by_portal,
    parse_supplier_selection,
)
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


def parse_suppliers_arg(value: str) -> list[str]:
    try:
        return parse_supplier_selection(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch supplier report(s) and test parser compatibility."
    )

    parser.add_argument(
        "--supplier",
        choices=SUPPORTED_SUPPLIERS,
        default=None,
        help="Single supplier to run. Kept for backwards compatibility.",
    )

    parser.add_argument(
        "--suppliers",
        type=parse_suppliers_arg,
        default=None,
        help=(
            "Comma-separated supplier list. Examples: citgo,valero | sunoco | "
            "citgo,valero,sunoco | dtn | all"
        ),
    )

    parser.add_argument(
        "--business-date",
        type=parse_business_date,
        default=date.today() - timedelta(days=1),
    )

    return parser


def resolve_suppliers(args) -> list[str]:
    if args.supplier and args.suppliers:
        raise SystemExit("Use either --supplier or --suppliers, not both.")

    if args.suppliers:
        return args.suppliers

    if args.supplier:
        return [args.supplier]

    raise SystemExit("Provide --supplier or --suppliers.")


def diagnostics_dir(settings, supplier_name: str, business_date: date) -> str:
    return str(settings.output_dir / "diagnostics" / supplier_name / str(business_date))


def issue_to_dict(issue) -> dict:
    return {
        "level": getattr(issue, "level", "UNKNOWN"),
        "message": getattr(issue, "message", str(issue)),
    }


def fetch_result_succeeded(fetch_result) -> bool:
    if hasattr(fetch_result, "succeeded"):
        return bool(fetch_result.succeeded)

    return getattr(fetch_result, "status", None) == "success"


def process_fetch_result_for_supplier(
    *,
    supplier_name: str,
    business_date: date,
    settings,
    fetch_result,
) -> bool:
    account = get_supplier_account(supplier_name)

    print_run_header(
        title=f"FETCH AND PARSE PROBE — {account.supplier_name.upper()}",
        supplier=account.supplier_name,
        portal=account.portal_name,
        business_date=business_date,
    )

    section("FETCH RESULT")

    if fetch_result is None:
        diagnostic_path = diagnostics_dir(
            settings=settings,
            supplier_name=account.supplier_name,
            business_date=business_date,
        )

        print("FETCH FAILED")
        status_line("Error", "No FetchResult was returned.")
        status_line("Diagnostics", diagnostic_path)
        print_final_status(success=False, diagnostics_path=diagnostic_path)
        return False

    if not fetch_result_succeeded(fetch_result):
        diagnostic_path = diagnostics_dir(
            settings=settings,
            supplier_name=account.supplier_name,
            business_date=business_date,
        )

        print("FETCH FAILED")
        status_line("Error", getattr(fetch_result, "error_message", "Unknown fetch error"))
        status_line("Diagnostics", diagnostic_path)
        print_final_status(success=False, diagnostics_path=diagnostic_path)
        return False

    print("Fetch completed successfully.")
    status_line("Stored Reports", len(fetch_result.stored_reports))

    supplier_success = True
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
                business_date=business_date,
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
            supplier_success = False

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
                business_date=business_date,
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
            supplier_success = False

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
            supplier_success = False

            diagnostic_path = write_diagnostic_record(
                DiagnosticRecord(
                    supplier_name=account.supplier_name,
                    portal_name=account.portal_name,
                    business_date=str(business_date),
                    step_name="validation_failed",
                    status="failed",
                    message="validate_report returned is_valid=False",
                    extra={
                        "raw_path": str(raw_path),
                        "file_hash": stored_report.file_hash,
                        "size_bytes": stored_report.size_bytes,
                        "report_supplier": getattr(report, "supplier", None),
                        "report_date": str(getattr(report, "report_date", "")),
                        "daily_totals_count": len(
                            getattr(report, "daily_totals", []) or []
                        ),
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
        success=supplier_success,
        diagnostics_path=last_diagnostic_path,
    )

    return supplier_success


def fetch_parse_validate_one_supplier(
    *,
    supplier_name: str,
    business_date: date,
    settings,
    download_manager: DownloadManager,
) -> bool:
    account = get_supplier_account(supplier_name)

    print_run_header(
        title=f"FETCH AND PARSE PROBE — {account.supplier_name.upper()}",
        supplier=account.supplier_name,
        portal=account.portal_name,
        business_date=business_date,
    )

    section("FETCH")
    print("Starting supplier fetch...")

    fetch_result = fetch_reports_for_account(
        account=account,
        business_date=business_date,
        download_manager=download_manager,
        remove_downloaded_files=True,
        raise_on_error=False,
    )

    return process_fetch_result_for_supplier(
        supplier_name=supplier_name,
        business_date=business_date,
        settings=settings,
        fetch_result=fetch_result,
    )


def fetch_parse_validate_dtn_group(
    *,
    supplier_names: list[str],
    business_date: date,
    settings,
    download_manager: DownloadManager,
) -> dict[str, bool]:
    section("DTN SHARED-LOGIN FETCH")
    status_line("Suppliers", ", ".join(supplier_names))
    print("Starting one DTN browser session for all requested DTN suppliers...")

    fetch_results = fetch_dtn_reports_for_supplier_group(
        supplier_names=supplier_names,
        business_date=business_date,
        download_manager=download_manager,
        settings=settings,
        remove_downloaded_files=True,
    )

    print("DTN group fetch completed. Processing each supplier result...")

    results: dict[str, bool] = {}

    for supplier_name in supplier_names:
        results[supplier_name] = process_fetch_result_for_supplier(
            supplier_name=supplier_name,
            business_date=business_date,
            settings=settings,
            fetch_result=fetch_results.get(supplier_name),
        )

    return results


def print_combined_summary(results: dict[str, bool]) -> None:
    section("COMBINED RUN SUMMARY")

    print(f"{'Supplier':<14} {'Status':<12}")
    print("-" * 30)

    for supplier_name, succeeded in results.items():
        status = "PASSED" if succeeded else "FAILED"
        print(f"{supplier_name:<14} {status:<12}")

    print("-" * 30)

    if all(results.values()):
        print("OVERALL STATUS: PASSED")
    else:
        print("OVERALL STATUS: FAILED")


def main() -> int:
    args = build_parser().parse_args()
    suppliers = resolve_suppliers(args)
    supplier_groups = group_suppliers_by_portal(suppliers)

    settings = get_settings()
    load_local_env(settings.project_root)

    download_manager = DownloadManager(settings=settings)

    section("MULTI-SUPPLIER FETCH AND PARSE")
    status_line("Business Date", args.business_date)
    status_line("Suppliers", ", ".join(suppliers))
    status_line(
        "Portal Groups",
        " | ".join(
            f"{group.portal_name}: {', '.join(group.supplier_names)}"
            for group in supplier_groups
        ),
    )

    results: dict[str, bool] = {}

    for group in supplier_groups:
        section(f"PORTAL GROUP — {group.portal_name.upper()}")
        status_line("Suppliers", ", ".join(group.supplier_names))

        if group.portal_name == "dtn" and len(group.supplier_names) > 1:
            group_results = fetch_parse_validate_dtn_group(
                supplier_names=group.supplier_names,
                business_date=args.business_date,
                settings=settings,
                download_manager=download_manager,
            )
            results.update(group_results)
            continue

        for supplier_name in group.supplier_names:
            succeeded = fetch_parse_validate_one_supplier(
                supplier_name=supplier_name,
                business_date=args.business_date,
                settings=settings,
                download_manager=download_manager,
            )

            results[supplier_name] = succeeded

    print_combined_summary(results)

    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())