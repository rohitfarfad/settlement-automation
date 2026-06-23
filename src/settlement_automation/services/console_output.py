from decimal import Decimal
from pathlib import Path

from settlement_automation.services.reconciliation import (
    get_mobile_adjustment_grand_total,
    summarize_mobile_adjustments,
)


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


def status_line(label: str, value) -> None:
    print(f"{label:<22}: {value}")


def safe_text(value, width: int) -> str:
    text = str(value or "")

    if len(text) > width:
        return text[: width - 3] + "..."

    return text


def print_run_header(title: str, supplier: str, portal: str, business_date) -> None:
    section(title)
    status_line("Supplier", supplier)
    status_line("Portal", portal)
    status_line("Business Date", business_date)


def print_raw_file_info(raw_path, file_hash=None, size_bytes=None) -> None:
    subsection("RAW FILE")

    status_line("Path", raw_path)

    if file_hash is not None:
        status_line("Hash", file_hash)

    if size_bytes is not None:
        status_line("Size", f"{size_bytes:,} bytes")


def print_report_summary(report, raw_path=None) -> None:
    subsection("REPORT SUMMARY")

    if raw_path is not None:
        status_line("Input File", raw_path)

    status_line("Supplier", getattr(report, "supplier", "UNKNOWN"))
    status_line("Report Date", getattr(report, "report_date", "UNKNOWN"))
    status_line("Daily Totals", len(getattr(report, "daily_totals", []) or []))
    status_line(
        "Mobile Adjustments",
        len(getattr(report, "mobile_adjustments", []) or []),
    )


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

    rows = sorted(rows, key=lambda row: (row.date, row.location_id, row.source_code or ""))

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
            f"{safe_text(row.source_code, 8):<8} "
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


def print_final_status(success: bool, diagnostics_path: str | Path | None = None) -> None:
    section("FINAL STATUS")

    if success:
        print("SUCCESS: Fetch, parse, and validation completed successfully.")
        return

    print("FAILED: Fetch and parse flow did not complete successfully.")

    if diagnostics_path:
        status_line("Diagnostics", diagnostics_path)