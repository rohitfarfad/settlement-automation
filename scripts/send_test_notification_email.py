from __future__ import annotations

from _path_setup import PROJECT_ROOT  # noqa: F401
import argparse
from datetime import date, datetime
from pathlib import Path

from settlement_automation.services.daily_run_summary import (
    RunError,
    build_daily_run_summary,
)
from settlement_automation.services.notifications import handle_daily_notification
from settlement_automation.services.report_processor import parse_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send a test notification email using a real parsed report."
    )

    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="Path to a downloaded raw report file.",
    )

    parser.add_argument(
        "--business-date",
        required=True,
        help="Business date for the report in YYYY-MM-DD format.",
    )

    parser.add_argument(
        "--supplier",
        default="valero",
        help="Supplier name used when auto-finding a report. Default: valero.",
    )

    return parser.parse_args()


def find_downloaded_report(
    *,
    supplier: str,
    business_date: date,
) -> Path:
    date_text = business_date.isoformat()
    supplier_text = supplier.lower()

    search_roots = [
        Path("data/tmp"),
        Path("data/incoming"),
        Path("data/raw"),
        Path("data/processed"),
    ]

    candidates: list[Path] = []

    for root in search_roots:
        if not root.exists():
            continue

        for path in root.rglob("*"):
            if not path.is_file():
                continue

            path_text = str(path).lower()

            if supplier_text not in path_text:
                continue

            if date_text not in path_text:
                continue

            if path.suffix.lower() not in {".txt", ".csv", ".json"}:
                continue

            candidates.append(path)

    if not candidates:
        raise FileNotFoundError(
            f"No downloaded {supplier} report found for {date_text}. "
            f"Pass the path explicitly using --file."
        )

    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0]


def main() -> None:
    args = parse_args()
    business_date = date.fromisoformat(args.business_date)

    report_path = args.file

    if report_path is None:
        report_path = find_downloaded_report(
            supplier=args.supplier,
            business_date=business_date,
        )

    if not report_path.exists():
        raise FileNotFoundError(f"Report file not found: {report_path}")

    print(f"Using report: {report_path}")

    started_at = datetime.now()
    errors: list[RunError] = []
    parsed_reports = []

    try:
        parsed_reports.append(parse_report(report_path))
    except Exception as exc:
        errors.append(
            RunError(
                stage="parse",
                supplier=args.supplier.upper(),
                message=f"Failed to parse report: {report_path}",
                exception_type=type(exc).__name__,
            )
        )

    finished_at = datetime.now()

    summary = build_daily_run_summary(
        business_date=business_date,
        run_date=date.today(),
        started_at=started_at,
        finished_at=finished_at,
        parsed_reports=parsed_reports,
        errors=errors,
    )

    result = handle_daily_notification(summary)

    print("Notification result")
    print("-------------------")
    print(f"Enabled      : {result.enabled}")
    print(f"Mode         : {result.mode}")
    print(f"Provider     : {result.provider}")
    print(f"Sent         : {result.sent}")
    print(f"Preview text : {result.preview_text_path}")
    print(f"Preview html : {result.preview_html_path}")

    if result.error_message:
        print(f"Error        : {result.error_message}")


if __name__ == "__main__":
    main()