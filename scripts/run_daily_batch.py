from __future__ import annotations

from _path_setup import PROJECT_ROOT  # noqa: F401

import argparse
import sys
import traceback
from datetime import date, datetime, timedelta

from config.settings import get_settings
from settlement_automation.services.daily_batch_notification import (
    DailyBatchRun,
    handle_daily_batch_notification,
)
from settlement_automation.services.daily_pipeline import (
    DailyPipelineResult,
    run_daily_fetch_parse_write_notify,
)
from settlement_automation.services.daily_run_artifacts import (
    write_daily_run_artifact,
)
from settlement_automation.services.run_lock import RunLock
from settlement_automation.utils.env import load_local_env


SUCCESS_EXIT_CODE = 0
HANDLED_FAILURE_EXIT_CODE = 1
CATASTROPHIC_FAILURE_EXIT_CODE = 2


def resolve_date(
    *,
    date_arg: str | None,
    days_back: int,
) -> date:
    if date_arg:
        return date.fromisoformat(date_arg)

    if days_back < 0:
        raise ValueError("days_back must be 0 or greater.")

    return date.today() - timedelta(days=days_back)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the daily settlement batch: "
            "CITGO/SUNOCO previous-day reports and VALERO current-day report."
        )
    )

    parser.add_argument(
        "--citgo-sunoco-report-date",
        help="Explicit CITGO/SUNOCO report date in YYYY-MM-DD format.",
    )

    parser.add_argument(
        "--citgo-sunoco-days-back",
        type=int,
        default=1,
        help="Default: 1, meaning yesterday.",
    )

    parser.add_argument(
        "--valero-report-date",
        help="Explicit VALERO report date in YYYY-MM-DD format.",
    )

    parser.add_argument(
        "--valero-days-back",
        type=int,
        default=0,
        help="Default: 0, meaning today.",
    )

    parser.add_argument(
        "--write-excel",
        action="store_true",
        help="Enable Excel writing.",
    )

    parser.add_argument(
        "--excel-dry-run",
        action="store_true",
        help="Resolve Excel writes without writing to workbooks.",
    )

    parser.add_argument(
        "--write-originals",
        action="store_true",
        help="Write directly to original workbooks.",
    )

    parser.add_argument(
        "--notify",
        action="store_true",
        help="Send or preview one combined batch notification.",
    )

    return parser


def print_run_summary(name: str, result: DailyPipelineResult) -> None:
    summary = result.summary

    print("")
    print(name)
    print("-" * 80)
    print(f"Report date           : {summary.report_date}")
    print(f"Suppliers parsed      : {', '.join(summary.supplier_names) or '-'}")
    print(f"Daily totals          : {summary.daily_total_count}")
    print(f"Excel written         : {summary.excel_written_count}")
    print(f"Excel skipped         : {summary.excel_skipped_count}")
    print(f"Warnings              : {summary.warning_count}")
    print(f"Errors                : {summary.error_count}")

    for error in summary.errors:
        supplier = f"[{error.supplier}] " if error.supplier else ""
        print(f"ERROR {error.stage.upper()}: {supplier}{error.message}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        load_local_env(PROJECT_ROOT)

        settings = get_settings()
        lock_path = settings.output_dir / "locks" / "daily_pipeline.lock"

        citgo_sunoco_report_date = resolve_date(
            date_arg=args.citgo_sunoco_report_date,
            days_back=args.citgo_sunoco_days_back,
        )

        valero_report_date = resolve_date(
            date_arg=args.valero_report_date,
            days_back=args.valero_days_back,
        )

        print("DAILY SETTLEMENT BATCH PIPELINE")
        print("=" * 80)
        print(f"Started at            : {datetime.now().isoformat(timespec='seconds')}")
        print(f"CITGO/SUNOCO date     : {citgo_sunoco_report_date}")
        print(f"VALERO date           : {valero_report_date}")
        print(f"Write Excel           : {args.write_excel}")
        print(f"Excel dry run         : {args.excel_dry_run}")
        print(f"Write originals       : {args.write_originals}")
        print(f"Combined notify       : {args.notify}")

        with RunLock(lock_path):
            citgo_sunoco_result = run_daily_fetch_parse_write_notify(
                report_date=citgo_sunoco_report_date,
                suppliers=["citgo", "sunoco"],
                write_excel=args.write_excel,
                excel_dry_run=args.excel_dry_run,
                write_originals=args.write_originals,
                notify=False,
            )

            citgo_sunoco_artifact = write_daily_run_artifact(citgo_sunoco_result)

            valero_result = run_daily_fetch_parse_write_notify(
                report_date=valero_report_date,
                suppliers=["valero"],
                write_excel=args.write_excel,
                excel_dry_run=args.excel_dry_run,
                write_originals=args.write_originals,
                notify=False,
            )

            valero_artifact = write_daily_run_artifact(valero_result)

            batch_notification_result = None

            if args.notify:
                batch_notification_result = handle_daily_batch_notification(
                    task_date=date.today(),
                    runs=[
                        DailyBatchRun(
                            name="CITGO + SUNOCO previous-day reports",
                            report_date=citgo_sunoco_report_date,
                            result=citgo_sunoco_result,
                        ),
                        DailyBatchRun(
                            name="VALERO current-day report",
                            report_date=valero_report_date,
                            result=valero_result,
                        ),
                    ],
                )

        print_run_summary(
            "CITGO + SUNOCO previous-day reports",
            citgo_sunoco_result,
        )
        print(f"Run artifact          : {citgo_sunoco_artifact}")

        print_run_summary(
            "VALERO current-day report",
            valero_result,
        )
        print(f"Run artifact          : {valero_artifact}")

        if batch_notification_result:
            print("")
            print("COMBINED NOTIFICATION")
            print("-" * 80)
            print(f"Enabled               : {batch_notification_result.enabled}")
            print(f"Mode                  : {batch_notification_result.mode}")
            print(f"Provider              : {batch_notification_result.provider}")
            print(f"Sent                  : {batch_notification_result.sent}")
            print(f"Preview text          : {batch_notification_result.preview_text_path}")
            print(f"Preview html          : {batch_notification_result.preview_html_path}")
            print(f"Error                 : {batch_notification_result.error_message}")

        has_errors = (
            citgo_sunoco_result.summary.has_errors
            or valero_result.summary.has_errors
            or (
                batch_notification_result is not None
                and batch_notification_result.error_message
            )
        )

        return HANDLED_FAILURE_EXIT_CODE if has_errors else SUCCESS_EXIT_CODE

    except RuntimeError as exc:
        message = str(exc)

        if "Another daily pipeline run is already in progress" in message:
            print("")
            print("DAILY PIPELINE ALREADY RUNNING")
            print("=" * 80)
            print(message)
            return HANDLED_FAILURE_EXIT_CODE

        raise

    except Exception as exc:
        print("")
        print("CATASTROPHIC DAILY BATCH PIPELINE FAILURE")
        print("=" * 80)
        print(f"Exception type        : {type(exc).__name__}")
        print(f"Message               : {exc}")
        print("")
        traceback.print_exc()
        return CATASTROPHIC_FAILURE_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())