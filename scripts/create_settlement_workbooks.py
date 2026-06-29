#!/usr/bin/env python3

"""
Create blank settlement Excel workbooks.

Naming convention:
    {YEAR} CC {LOCATION_NAME} {SUPPLIER}.xlsx

Example:
    2026 CC HAVERSTRAW VALERO.xlsx
    2026 CC MONTECELLO VALERO.xlsx

Workbook structure:
    One workbook per supplier/location.
    12 monthly sheets:
        JAN 2026, FEB 2026, ..., DEC 2026

Each monthly sheet has:
    DATE
    STORE AMT
    DIFF
    GROSS AMT
    NET AMT
    CC FEE
    DATE OF VALERO CREDIT
    MONTHLY VAL CHGS IN FEES
    FUELMAN
    MOBILE PAY ADDED TO GROSS/NET
    VALERO PAY +
    GIFT CARDS
"""
from __future__ import annotations
from _path_setup import PROJECT_ROOT  # noqa: F401
import argparse
import calendar
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from config.locations import CITGO_LOCATIONS, VALERO_LOCATIONS, SUNOCO_LOCATIONS


MONTH_ABBR = [
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
]


SETTLEMENT_COLUMNS = [
    "DATE",
    "STORE AMT",
    "DIFF",
    "GROSS AMT",
    "NET AMT",
    "CC FEE",
    "DATE OF VALERO CREDIT",
    "MONTHLY VAL CHGS IN FEES",
    "FUELMAN",
    "MOBILE PAY ADDED TO GROSS/NET",
    "VALERO PAY +",
    "GIFT CARDS",
]


@dataclass(frozen=True)
class SettlementWorkbookTarget:
    supplier: str
    location_id: str
    location_name: str


# Keep this mapping aligned with config/excel_mapping.py and config/locations.py.
# The filename uses location_name, not location_id.

LOCATION_MAPS = {
    "CITGO": CITGO_LOCATIONS,
    "VALERO": VALERO_LOCATIONS,
    "SUNOCO": SUNOCO_LOCATIONS,
}


WORKBOOK_TARGETS: list[SettlementWorkbookTarget] = [
    SettlementWorkbookTarget(
        supplier=supplier,
        location_id=location_id,
        location_name=location_name,
    )
    for supplier, locations in LOCATION_MAPS.items()
    for location_id, location_name in locations.items()
]


def normalize_for_filename(value: str) -> str:
    """
    Normalize names for workbook filenames.

    Keeps spaces because the existing naming convention uses spaces:
        2026 CC MONTECELLO VALERO.xlsx
    """
    value = value.strip().upper()
    value = re.sub(r"[\\/:*?\"<>|]", "", value)
    value = re.sub(r"\s+", " ", value)
    return value


def build_workbook_filename(year: int, location_name: str, supplier: str) -> str:
    location_name = normalize_for_filename(location_name)
    supplier = normalize_for_filename(supplier)

    # Avoid names like:
    #   2026 CC FIVE CORNERS VALERO VALERO.xlsx
    #
    # If location already ends with supplier name, do not append supplier again.
    if location_name.endswith(supplier):
        return f"{year} CC {location_name}.xlsx"

    return f"{year} CC {location_name} {supplier}.xlsx"

def build_sheet_name(year: int, month: int) -> str:
    return f"{MONTH_ABBR[month - 1]} {year}"


def style_month_sheet(ws, year: int, month: int, supplier: str, location_name: str) -> None:
    title_fill = PatternFill("solid", fgColor="D9EAF7")
    header_fill = PatternFill("solid", fgColor="BDD7EE")
    thin = Side(style="thin", color="B7B7B7")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    max_col = len(SETTLEMENT_COLUMNS)
    last_col_letter = get_column_letter(max_col)

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max_col)
    ws["A1"] = f"{supplier.upper()} SETTLEMENT - {location_name.upper()} - {build_sheet_name(year, month)}"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A1"].fill = title_fill
    ws["A1"].alignment = Alignment(horizontal="center")

    for col_idx, header in enumerate(SETTLEMENT_COLUMNS, start=1):
        cell = ws.cell(row=2, column=col_idx)
        cell.value = header
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    days_in_month = calendar.monthrange(year, month)[1]

    for day in range(1, days_in_month + 1):
        row = day + 2
        current_date = date(year, month, day)

        ws.cell(row=row, column=1).value = current_date
        ws.cell(row=row, column=1).number_format = "m/d/yyyy"

        # DIFF = STORE AMT - GROSS AMT
        ws.cell(row=row, column=3).value = f'=IF(OR(B{row}="",D{row}=""),"",ROUND(B{row}-D{row},2))'

        # CC FEE = GROSS AMT - NET AMT
        # The Excel writer should not overwrite this column; it should only validate it.
        ws.cell(row=row, column=6).value = f'=IF(OR(D{row}="",E{row}=""),"",ROUND(D{row}-E{row},2))'

        for col_idx in range(1, max_col + 1):
            cell = ws.cell(row=row, column=col_idx)
            cell.border = border
            cell.alignment = Alignment(horizontal="center", vertical="center")

            if col_idx in {2, 3, 4, 5, 6, 8, 9, 10, 11, 12}:
                cell.number_format = '#,##0.00'

    total_row = days_in_month + 4
    ws.cell(row=total_row, column=1).value = "MONTH TOTAL"
    ws.cell(row=total_row, column=1).font = Font(bold=True)

    for col_idx in [2, 3, 4, 5, 6, 8, 9, 10, 11, 12]:
        col_letter = get_column_letter(col_idx)
        ws.cell(row=total_row, column=col_idx).value = f"=SUM({col_letter}3:{col_letter}{days_in_month + 2})"
        ws.cell(row=total_row, column=col_idx).font = Font(bold=True)
        ws.cell(row=total_row, column=col_idx).number_format = '#,##0.00'

    for col_idx in range(1, max_col + 1):
        ws.cell(row=total_row, column=col_idx).border = border

    ws.freeze_panes = "A3"
    ws.auto_filter.ref = f"A2:{last_col_letter}{days_in_month + 2}"

    widths = {
        "A": 13,
        "B": 13,
        "C": 11,
        "D": 13,
        "E": 13,
        "F": 11,
        "G": 22,
        "H": 24,
        "I": 12,
        "J": 28,
        "K": 14,
        "L": 13,
    }

    for col_letter, width in widths.items():
        ws.column_dimensions[col_letter].width = width

    ws.row_dimensions[1].height = 24
    ws.row_dimensions[2].height = 36


def create_settlement_workbook(
    output_path: Path,
    year: int,
    supplier: str,
    location_name: str,
) -> None:
    wb = Workbook()

    # Remove default sheet.
    default_ws = wb.active
    wb.remove(default_ws)

    for month in range(1, 13):
        ws = wb.create_sheet(title=build_sheet_name(year, month))
        style_month_sheet(
            ws=ws,
            year=year,
            month=month,
            supplier=supplier,
            location_name=location_name,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)


def filter_targets(
    supplier: str | None,
    location_id: str | None,
    location_name: str | None,
) -> list[SettlementWorkbookTarget]:
    targets = WORKBOOK_TARGETS

    if supplier:
        supplier_upper = supplier.upper()
        targets = [t for t in targets if t.supplier.upper() == supplier_upper]

    if location_id:
        targets = [t for t in targets if t.location_id == location_id]

    if location_name:
        name_upper = location_name.upper()
        targets = [t for t in targets if t.location_name.upper() == name_upper]

    return targets


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create blank settlement Excel workbooks."
    )
    parser.add_argument(
        "--year",
        type=int,
        required=True,
        help="Settlement workbook year, e.g. 2026.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/excel/settlements"),
        help="Directory where workbooks should be created.",
    )
    parser.add_argument(
        "--supplier",
        help="Optional supplier filter, e.g. VALERO, CITGO, SUNOCO.",
    )
    parser.add_argument(
        "--location-id",
        help="Optional location id filter, e.g. 15861002.",
    )
    parser.add_argument(
        "--location-name",
        help="Optional location name filter, e.g. HAVERSTRAW.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing workbooks.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print files that would be created without creating them.",
    )

    args = parser.parse_args()

    targets = filter_targets(
        supplier=args.supplier,
        location_id=args.location_id,
        location_name=args.location_name,
    )

    if not targets:
        raise SystemExit("No workbook targets matched the given filters.")

    created = 0
    skipped = 0

    for target in targets:
        filename = build_workbook_filename(
            year=args.year,
            location_name=target.location_name,
            supplier=target.supplier,
        )
        output_path = args.output_dir / filename

        if args.dry_run:
            print(f"[DRY RUN] Would create: {output_path}")
            continue

        if output_path.exists() and not args.overwrite:
            print(f"[SKIP] Exists already: {output_path}")
            skipped += 1
            continue

        create_settlement_workbook(
            output_path=output_path,
            year=args.year,
            supplier=target.supplier,
            location_name=target.location_name,
        )
        print(f"[CREATE] {output_path}")
        created += 1

    print()
    print(f"Created : {created}")
    print(f"Skipped : {skipped}")
    print(f"Dry run : {args.dry_run}")


if __name__ == "__main__":
    main()