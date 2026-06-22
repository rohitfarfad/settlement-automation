import argparse
from decimal import Decimal

from settlement_automation.services.report_processor import parse_report
from settlement_automation.services.report_detector import detect_supplier
from settlement_automation.services.validation import validate_report
from settlement_automation.services.reconciliation import (
    summarize_mobile_adjustments,
    get_mobile_adjustment_grand_total,
)
from settlement_automation.services.audit_exporter import export_audit_files

def money(value: Decimal) -> str:
    return f"${value:,.2f}"


def print_daily_totals(rows):
    print("\nDAILY TOTALS")
    print("-" * 100)

    if not rows:
        print("No daily totals found")
        return

    for row in rows:
        print(
            f"{row.date} | "
            f"{row.location_id} | "
            f"{row.location_name:<25} | "
            f"Gross: {money(row.gross_amt):>12} | "
            f"Fees: {money(row.fees):>10} | "
            f"Net: {money(row.net_amt):>12}"
        )


def print_mobile_adjustments(rows):
    print("\nBACKDATED MOBILE ADJUSTMENTS")
    print("-" * 100)

    if not rows:
        print("No backdated mobile adjustments found")
        return

    for row in rows:
        print(
            f"{row.date} | "
            f"{row.location_id} | "
            f"{row.location_name:<25} | "
            f"{row.source_code:<5} | "
            f"Gross: {money(row.gross_amt):>12} | "
            f"Fees: {money(row.fees):>10} | "
            f"Net: {money(row.net_amt):>12}"
        )

def print_validation_result(result):
    print("\nVALIDATION")
    print("-" * 100)

    if result.is_valid and not result.issues:
        print("PASSED: No validation issues found.")
        return

    for issue in result.issues:
        print(f"{issue.level}: {issue.message}")

    if result.is_valid:
        print("\nPASSED WITH WARNINGS")
    else:
        print("\nFAILED")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--export-csv", action="store_true")
    parser.add_argument("--output-dir", default="output/reports")

    args = parser.parse_args()

    report = parse_report(args.file)
    validation_result = validate_report(report)

    print(f"\nSupplier: {report.supplier}")
    print(f"Report Date: {report.report_date}")

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

        print("\nEXPORTED AUDIT FILES")
        print("-" * 100)

        for file_path in exported_files:
            print(file_path)

def print_mobile_adjustment_summary(rows):
    print("\nBACKDATED MOBILE ADJUSTMENTS SUMMARY")
    print("-" * 100)

    if not rows:
        print("No backdated mobile adjustment summary found")
        return

    summary_rows = summarize_mobile_adjustments(rows)

    for row in summary_rows:
        print(
            f"{row.date} | "
            f"{row.location_id} | "
            f"{row.location_name:<25} | "
            f"Gross: {money(row.gross_amt):>12} | "
            f"Fees: {money(row.fees):>10} | "
            f"Net: {money(row.net_amt):>12}"
        )

    gross, fees, net = get_mobile_adjustment_grand_total(rows)

    print("-" * 100)
    print(
        f"{'GRAND TOTAL':<39} | "
        f"Gross: {money(gross):>12} | "
        f"Fees: {money(fees):>10} | "
        f"Net: {money(net):>12}"
    )
if __name__ == "__main__":
    main()