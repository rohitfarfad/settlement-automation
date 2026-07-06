from __future__ import annotations

from _path_setup import PROJECT_ROOT  # noqa: F401
from config.settings import get_settings
from settlement_automation.utils.env import load_local_env
import argparse
import sys
import traceback
from datetime import date, datetime, timedelta

from settlement_automation.ingestion.supplier_selection import parse_supplier_selection
from settlement_automation.services.daily_pipeline import (
    run_daily_fetch_parse_write_notify,
)
SUCCESS_EXIT_CODE = 0
HANDLED_FAILURE_EXIT_CODE = 1
CATASTROPHIC_FAILURE_EXIT_CODE = 2


def parse_suppliers_arg(value: str) -> list[str]:
    try:
        return parse_supplier_selection(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def resolve_report_date(
    *,
    report_date_arg: str | None,
    days_back: int,
) -> date:
    if report_date_arg:
        return date.fromisoformat(report_date_arg)

    if days_back < 0:
        raise ValueError("--days-back must be 0 or greater.")

    return date.today() - timedelta(days=days_back)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the daily settlement pipeline for one report date. "
            "By default, processes yesterday's report."
        )
    )

    parser.add_argument(
        "--report-date",
        help=(
            "Report date in YYYY-MM-DD format. "
            "If omitted, defaults to today minus --days-back."
        ),
    )

    parser.add_argument(
        "--days-back",
        type=int,
        default=1,
        help=(
            "Number of days before today to process when --report-date is omitted. "
            "Default: 1, meaning yesterday's report."
        ),
    )

    parser.add_argument(
        "--suppliers",
        type=parse_suppliers_arg,
        default=parse_supplier_selection("all"),
        help=(
            "Supplier selection: all, dtn, citgo, valero, sunoco, "
            "or comma-separated list like citgo,valero. Default: all."
        ),
    )

    parser.add_argument(
        "--write-excel",
        action="store_true",
        help="Enable Excel writing. If omitted, only parse/validate/notify.",
    )

    parser.add_argument(
        "--excel-dry-run",
        action="store_true",
        help="Resolve Excel writes without writing to workbooks.",
    )

    parser.add_argument(
        "--write-originals",
        action="store_true",
        help="Write directly to original workbooks instead of output copies.",
    )

    parser.add_argument(
        "--notify",
        action="store_true",
        help="Send or preview notification based on notification env config.",
    )

    return parser


def print_result_summary(result) -> None:
    summary = result.summary

    print("")
    print("DAILY PIPELINE RESULT")
    print("=" * 80)
    print(f"Run date              : {summary.run_date}")
    print(f"Report date           : {summary.report_date}")
    print(f"Suppliers parsed      : {', '.join(summary.supplier_names) or '-'}")
    print(f"Daily totals          : {summary.daily_total_count}")
    print(f"Mobile adjustments    : {summary.mobile_adjustment_count}")
    print(f"Valero Pay+ rows      : {summary.valero_pay_plus_count}")
    print(f"Monthly charges       : {summary.valero_monthly_charge_count}")
    print(f"Unclassified adj      : {summary.unclassified_adjustment_count}")
    print(f"Excel written         : {summary.excel_written_count}")
    print(f"Excel skipped         : {summary.excel_skipped_count}")
    print(f"Warnings              : {summary.warning_count}")
    print(f"Errors                : {summary.error_count}")

    if summary.errors:
        print("")
        print("ERRORS")
        print("-" * 80)
        for error in summary.errors:
            supplier = f"[{error.supplier}] " if error.supplier else ""
            exception = (
                f" ({error.exception_type})"
                if error.exception_type
                else ""
            )
            print(f"- {error.stage.upper()} {supplier}{error.message}{exception}")

    if summary.warnings:
        print("")
        print("WARNINGS")
        print("-" * 80)
        for warning in summary.warnings:
            print(f"- {warning}")

    if result.notification_result:
        notification = result.notification_result

        print("")
        print("NOTIFICATION")
        print("-" * 80)
        print(f"Enabled               : {notification.enabled}")
        print(f"Mode                  : {notification.mode}")
        print(f"Provider              : {notification.provider}")
        print(f"Sent                  : {notification.sent}")
        print(f"Preview text          : {notification.preview_text_path}")
        print(f"Preview html          : {notification.preview_html_path}")

        if notification.error_message:
            print(f"Error                 : {notification.error_message}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        settings = get_settings()
        load_local_env(settings.project_root)
        report_date = resolve_report_date(
            report_date_arg=args.report_date,
            days_back=args.days_back,
        )

        print("DAILY SETTLEMENT PIPELINE")
        print("=" * 80)
        print(f"Started at            : {datetime.now().isoformat(timespec='seconds')}")
        print(f"Report date           : {report_date}")
        print(f"Suppliers             : {', '.join(args.suppliers)}")
        print(f"Write Excel           : {args.write_excel}")
        print(f"Excel dry run         : {args.excel_dry_run}")
        print(f"Write originals       : {args.write_originals}")
        print(f"Notify                : {args.notify}")

        # Step 1 intentionally uses the existing parse/write/notify service.
        # Step 2 will replace this call with run_daily_fetch_parse_write_notify().
        result = run_daily_fetch_parse_write_notify(
            report_date=report_date,
            suppliers=args.suppliers,
            write_excel=args.write_excel,
            excel_dry_run=args.excel_dry_run,
            write_originals=args.write_originals,
            notify=args.notify,
        )

        print_result_summary(result)

        if result.summary.has_errors:
            return HANDLED_FAILURE_EXIT_CODE

        if result.notification_result and result.notification_result.error_message:
            return HANDLED_FAILURE_EXIT_CODE

        return SUCCESS_EXIT_CODE

    except Exception as exc:
        print("")
        print("CATASTROPHIC DAILY PIPELINE FAILURE")
        print("=" * 80)
        print(f"Exception type        : {type(exc).__name__}")
        print(f"Message               : {exc}")
        print("")
        traceback.print_exc()
        return CATASTROPHIC_FAILURE_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())