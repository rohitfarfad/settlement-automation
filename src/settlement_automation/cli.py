import sys
from pathlib import Path

from settlement_automation.services.console_output import (
    print_daily_totals,
    print_mobile_adjustments,
    print_mobile_adjustment_summary,
    print_report_summary,
    print_validation_result,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"

for path in (PROJECT_ROOT, SRC_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


import argparse
from decimal import Decimal

from settlement_automation.services.reconciliation import (
    summarize_mobile_adjustments,
    get_mobile_adjustment_grand_total,
    summarize_valero_pay_plus_adjustments,
    get_valero_pay_plus_grand_total, get_valero_monthly_charges_grand_total, summarize_valero_monthly_charges,
    summarize_sunoco_credit_card_discounts,
    get_sunoco_credit_card_discounts_grand_total,
)

from settlement_automation.services.report_processor import parse_report
from settlement_automation.services.validation import validate_report
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

def print_valero_pay_plus_adjustments(rows) -> None:
    subsection("VALERO PAY+ ADJUSTMENTS")

    if not rows:
        print("No Valero Pay+ adjustments found.")
        return

    rows = sorted(rows, key=lambda row: (row.date, row.location_id, row.source_code or ""))

    print(
        f"{'Date':<12} "
        f"{'Location ID':<14} "
        f"{'Location Name':<28} "
        f"{'Source':<8} "
        f"{'Amount':>14}"
    )
    print("-" * LINE_WIDTH)

    for row in rows:
        print(
            f"{str(row.date):<12} "
            f"{row.location_id:<14} "
            f"{safe_text(row.location_name, 28):<28} "
            f"{(row.source_code or ''):<8} "
            f"{money(row.amount):>14}"
        )


def print_valero_pay_plus_summary(rows) -> None:
    subsection("VALERO PAY+ SUMMARY")

    if not rows:
        print("No Valero Pay+ summary found.")
        return

    summary_rows = summarize_valero_pay_plus_adjustments(rows)

    print(
        f"{'Date':<12} "
        f"{'Location ID':<14} "
        f"{'Location Name':<28} "
        f"{'Amount':>14}"
    )
    print("-" * LINE_WIDTH)

    for row in summary_rows:
        print(
            f"{str(row.date):<12} "
            f"{row.location_id:<14} "
            f"{safe_text(row.location_name, 28):<28} "
            f"{money(row.amount):>14}"
        )

    total = get_valero_pay_plus_grand_total(rows)

    print("-" * LINE_WIDTH)
    print(
        f"{'GRAND TOTAL':<12} "
        f"{'':<14} "
        f"{'':<28} "
        f"{money(total):>14}"
    )

def print_valero_monthly_charges(rows) -> None:
    subsection("VALERO MONTHLY CHARGES")

    if not rows:
        print("No Valero monthly charges found.")
        return

    rows = sorted(rows, key=lambda row: (row.date, row.location_id, row.description))

    print(
        f"{'Date':<12} "
        f"{'Location ID':<14} "
        f"{'Location Name':<28} "
        f"{'Amount':>14} "
        f"{'Description'}"
    )
    print("-" * LINE_WIDTH)

    for row in rows:
        print(
            f"{str(row.date):<12} "
            f"{row.location_id:<14} "
            f"{safe_text(row.location_name, 28):<28} "
            f"{money(row.amount):>14} "
            f"{row.description}"
        )


def print_valero_monthly_charges_summary(rows) -> None:
    subsection("VALERO MONTHLY CHARGES SUMMARY")

    if not rows:
        print("No Valero monthly charge summary found.")
        return

    summary_rows = summarize_valero_monthly_charges(rows)

    print(
        f"{'Date':<12} "
        f"{'Location ID':<14} "
        f"{'Location Name':<28} "
        f"{'Amount':>14}"
    )
    print("-" * LINE_WIDTH)

    for row in summary_rows:
        print(
            f"{str(row.date):<12} "
            f"{row.location_id:<14} "
            f"{safe_text(row.location_name, 28):<28} "
            f"{money(row.amount):>14}"
        )

    total = get_valero_monthly_charges_grand_total(rows)

    print("-" * LINE_WIDTH)
    print(
        f"{'GRAND TOTAL':<12} "
        f"{'':<14} "
        f"{'':<28} "
        f"{money(total):>14}"
    )

def print_sunoco_credit_card_discounts_summary(rows) -> None:
    subsection("SUNOCO CREDIT CARD DISCOUNTS - SUMMARY")

    if not rows:
        print("No SUNOCO credit card discounts found.")
        return

    summary_rows = summarize_sunoco_credit_card_discounts(rows)

    print(
        f"{'Date':<12} "
        f"{'Location ID':<14} "
        f"{'Location Name':<28} "
        f"{'Amount':>14}"
    )
    print("-" * LINE_WIDTH)

    for row in summary_rows:
        print(
            f"{str(row.date):<12} "
            f"{row.location_id:<14} "
            f"{safe_text(row.location_name, 28):<28} "
            f"{money(row.amount):>14}"
        )

    total = get_sunoco_credit_card_discounts_grand_total(rows)

    print("-" * LINE_WIDTH)
    print(
        f"{'GRAND TOTAL':<12} "
        f"{'':<14} "
        f"{'':<28} "
        f"{money(total):>14}"
    )


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

    print_report_summary(report, raw_path=args.file)
    print_daily_totals(report.daily_totals)
    #print_mobile_adjustments(report.mobile_adjustments)
    print_mobile_adjustment_summary(report.mobile_adjustments)
    pay_plus_rows = getattr(report, "valero_pay_plus_adjustments", [])
    #print_valero_pay_plus_adjustments(pay_plus_rows)
    print_valero_pay_plus_summary(pay_plus_rows)
    print_validation_result(validation_result)
    monthly_charge_rows = getattr(report, "valero_monthly_charges", [])
    #print_valero_monthly_charges(monthly_charge_rows)
    print_valero_monthly_charges_summary(monthly_charge_rows)
    sunoco_discount_rows = getattr(report, "sunoco_credit_card_discounts", [])

    print_sunoco_credit_card_discounts_summary(sunoco_discount_rows)

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
