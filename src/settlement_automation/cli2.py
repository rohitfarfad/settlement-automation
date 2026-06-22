import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"

for path in (PROJECT_ROOT, SRC_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


import argparse
from decimal import Decimal

from settlement_automation.services.report_processor import parse_report
from settlement_automation.services.validation import validate_report
from settlement_automation.services.reconciliation import (
    summarize_mobile_adjustments,
    get_mobile_adjustment_grand_total,
)
from settlement_automation.services.audit_exporter import export_audit_files


LINE_WIDTH = 118


def money(value: Decimal | None) -> str:
    if value is None:
        return ""

    value = Decimal(value)

    if value < 0:
        return f"-${abs(value):,.2f}"

    return f"${value:,.2f}"


def section(title: str) -> None:
    print(f"\n{title}")
    print("=" * LINE_WIDTH)


def subsection(title: str) -> None:
    print(f"\n{title}")
    print("-" * LINE_WIDTH)


def safe_text(value, width: int) -> str:
    text = str(value or "")

    if len(text) > width:
        return text[: width - 3] + "..."

    return text


def print_report_header(report, file_path: str) -> None:
    section("REPORT SUMMARY")

    print(f"{'Input File':<18}: {file_path}")
    print(f"{'Supplier':<18}: {getattr(report, 'supplier', 'UNKNOWN')}")
    print(f"{'Report Date':<18}: {getattr(report, 'report_date', 'UNKNOWN')}")
    print(f"{'Daily Totals':<18}: {len(getattr(report, 'daily_totals', []) or [])}")
    print(f"{'Mobile Adjustments':<18}: {len(getattr(report, 'mobile_adjustments', []) or [])}")


def print_daily_totals(rows) -> None:
    subsection("DAILY TOTALS")

    if not rows:
        print("No daily totals found.")
        return

    rows = sorted(rows, key=lambda row: (row.date, row.location_id))

    print(
        f"{'Date':<12} "
        f"{'Location ID':<14} "
        f"{'Location Name':<28} "
        f"{'Gross':>14} "
        f"{'Fees':>14} "
        f"{'Net':>14}"
    )
    print("-" * LINE_WIDTH)

    total_gross = Decimal("0")
    total_fees = Decimal("0")
    total_net = Decimal("0")

    for row in rows:
        total_gross += row.gross_amt
        total_fees += row.fees
        total_net += row.net_amt

        print(
            f"{str(row.date):<12} "
            f"{row.location_id:<14} "
            f"{safe_text(row.location_name, 28):<28} "
            f"{money(row.gross_amt):>14} "
            f"{money(row.fees):>14} "
            f"{money(row.net_amt):>14}"
        )

    print("-" * LINE_WIDTH)
    print(
        f"{'TOTAL':<12} "
        f"{'':<14} "
        f"{'':<28} "
        f"{money(total_gross):>14} "
        f"{money(total_fees):>14} "
        f"{money(total_net):>14}"
    )


def print_mobile_adjustments(rows) -> None:
    subsection("BACKDATED MOBILE ADJUSTMENTS")

    if not rows:
        print("No backdated mobile adjustments found.")
        return

    rows = sorted(rows, key=lambda row: (row.date, row.location_id, row.source_code))

    print(
        f"{'Date':<12} "
        f"{'Location ID':<14} "
        f"{'Location Name':<28} "
        f"{'Source':<8} "
        f"{'Gross':>14} "
        f"{'Fees':>14} "
        f"{'Net':>14}"
    )
    print("-" * LINE_WIDTH)

    for row in rows:
        print(
            f"{str(row.date):<12} "
            f"{row.location_id:<14} "
            f"{safe_text(row.location_name, 28):<28} "
            f"{row.source_code:<8} "
            f"{money(row.gross_amt):>14} "
            f"{money(row.fees):>14} "
            f"{money(row.net_amt):>14}"
        )


def print_mobile_adjustment_summary(rows) -> None:
    subsection("BACKDATED MOBILE ADJUSTMENTS SUMMARY")

    if not rows:
        print("No backdated mobile adjustment summary found.")
        return

    summary_rows = summarize_mobile_adjustments(rows)
    summary_rows = sorted(summary_rows, key=lambda row: (row.date, row.location_id))

    print(
        f"{'Date':<12} "
        f"{'Location ID':<14} "
        f"{'Location Name':<28} "
        f"{'Gross':>14} "
        f"{'Fees':>14} "
        f"{'Net':>14}"
    )
    print("-" * LINE_WIDTH)

    for row in summary_rows:
        print(
            f"{str(row.date):<12} "
            f"{row.location_id:<14} "
            f"{safe_text(row.location_name, 28):<28} "
            f"{money(row.gross_amt):>14} "
            f"{money(row.fees):>14} "
            f"{money(row.net_amt):>14}"
        )

    gross, fees, net = get_mobile_adjustment_grand_total(rows)

    print("-" * LINE_WIDTH)
    print(
        f"{'GRAND TOTAL':<12} "
        f"{'':<14} "
        f"{'':<28} "
        f"{money(gross):>14} "
        f"{money(fees):>14} "
        f"{money(net):>14}"
    )


def print_validation_result(result) -> None:
    subsection("VALIDATION")

    issues = result.issues or []

    errors = [issue for issue in issues if issue.level.upper() == "ERROR"]
    warnings = [issue for issue in issues if issue.level.upper() == "WARNING"]
    others = [
        issue
        for issue in issues
        if issue.level.upper() not in {"ERROR", "WARNING"}
    ]

    if result.is_valid and not issues:
        print("PASSED: No validation issues found.")
        return

    if errors:
        print(f"ERRORS ({len(errors)})")
        for index, issue in enumerate(errors, start=1):
            print(f"  {index}. {issue.message}")

    if warnings:
        if errors:
            print()

        print(f"WARNINGS ({len(warnings)})")
        for index, issue in enumerate(warnings, start=1):
            print(f"  {index}. {issue.message}")

    if others:
        if errors or warnings:
            print()

        print(f"OTHER ISSUES ({len(others)})")
        for index, issue in enumerate(others, start=1):
            print(f"  {index}. [{issue.level}] {issue.message}")

    print()
    if result.is_valid:
        print("STATUS: PASSED WITH WARNINGS")
    else:
        print("STATUS: FAILED")


def print_exported_files(exported_files) -> None:
    subsection("EXPORTED AUDIT FILES")

    if not exported_files:
        print("No audit files exported.")
        return

    for file_path in exported_files:
        print(file_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse and validate a supplier settlement report."
    )

    parser.add_argument(
        "--file",
        required=True,
        help="Path to supplier report file.",
    )

    parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview parsed output. Kept for compatibility; output is printed by default.",
    )

    parser.add_argument(
        "--export-csv",
        action="store_true",
        help="Export audit CSV files.",
    )

    parser.add_argument(
        "--output-dir",
        default="output/reports",
        help="Directory for exported audit files.",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    file_path = Path(args.file)

    if not file_path.exists():
        print(f"ERROR: File not found: {file_path}")
        return 1

    report = parse_report(str(file_path))
    validation_result = validate_report(report)

    print_report_header(report, str(file_path))
    print_daily_totals(report.daily_totals)
    print_mobile_adjustments(report.mobile_adjustments)
    print_mobile_adjustment_summary(report.mobile_adjustments)
    print_validation_result(validation_result)

    if args.export_csv:
        exported_files = export_audit_files(
            report=report,
            validation_result=validation_result,
            output_dir=args.output_dir,
        )
        print_exported_files(exported_files)

    return 0 if validation_result.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())

#python src/settlement_automation/cli.py --file data/tmp/dtn/citgo/2026-06-17/citgo_click_capture_2026-06-17_row_2.txt
