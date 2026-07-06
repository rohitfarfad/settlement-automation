from __future__ import annotations

from _path_setup import PROJECT_ROOT  # noqa: F401
import argparse
from datetime import date

from settlement_automation.services.daily_pipeline import (
    run_daily_parse_write_notify,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse, write, and notify for one or more suppliers."
    )

    parser.add_argument(
        "--report-date",
        help="Report date in YYYY-MM-DD format.",
    )

    parser.add_argument(
        "--business-date",
        help=(
            "Deprecated alias for --report-date. "
            "Use --report-date going forward."
        ),
    )

    parser.add_argument(
        "--suppliers",
        nargs="+",
        required=True,
        help="Suppliers to process, e.g. valero citgo sunoco.",
    )

    parser.add_argument(
        "--write-excel",
        action="store_true",
        help="Enable Excel writing. If omitted, only parse/validate/notify.",
    )

    parser.add_argument(
        "--excel-dry-run",
        action="store_true",
        help="Build/resolve Excel writes without writing originals.",
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

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    report_date = date.fromisoformat(args.report_date)

    result = run_daily_parse_write_notify(
        report_date=report_date,
        suppliers=args.suppliers,
        write_excel=args.write_excel,
        excel_dry_run=args.excel_dry_run,
        write_originals=args.write_originals,
        notify=args.notify,
    )

    summary = result.summary

    print("DAILY PIPELINE RESULT")
    print("=" * 80)
    print(f"Business date        : {summary.business_date}")
    print(f"Suppliers parsed     : {', '.join(summary.supplier_names) or '-'}")
    print(f"Daily totals         : {summary.daily_total_count}")
    print(f"Mobile adjustments   : {summary.mobile_adjustment_count}")
    print(f"Valero Pay+ rows     : {summary.valero_pay_plus_count}")
    print(f"Monthly charges      : {summary.valero_monthly_charge_count}")
    print(f"Unclassified adj     : {summary.unclassified_adjustment_count}")
    print(f"Warnings             : {summary.warning_count}")
    print(f"Errors               : {summary.error_count}")

    if result.notification_result:
        notification = result.notification_result
        print("")
        print("NOTIFICATION")
        print("-" * 80)
        print(f"Enabled              : {notification.enabled}")
        print(f"Mode                 : {notification.mode}")
        print(f"Provider             : {notification.provider}")
        print(f"Sent                 : {notification.sent}")
        print(f"Preview text         : {notification.preview_text_path}")
        print(f"Preview html         : {notification.preview_html_path}")

        if notification.error_message:
            print(f"Error                : {notification.error_message}")


if __name__ == "__main__":
    main()