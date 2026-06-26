from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from decimal import Decimal
from config.locations import CITGO_LOCATIONS, SUNOCO_LOCATIONS, VALERO_LOCATIONS


class ExcelWriteMode(str, Enum):
    SET = "set"
    ADD = "add"
    PRESERVE_FORMULA = "preserve_formula"


class MissingTargetPolicy(str, Enum):
    WARN_AND_SKIP = "warn_and_skip"
    ERROR = "error"


@dataclass(frozen=True)
class ExcelColumnHeaders:
    date: str = "Date"
    gross_amt: str = "Gross AMT"
    net_amt: str = "NET AMT"
    fees: str = "CC Fee"
    mobile_pay: str = "MOBILE PAY ADDED TO GROSS/NET"


@dataclass(frozen=True)
class ValeroMobileAdjustmentPolicy:
    aggregate_before_write: bool = True

    # Daily total values are treated as the base values.
    gross_behavior: ExcelWriteMode = ExcelWriteMode.SET
    net_behavior: ExcelWriteMode = ExcelWriteMode.SET

    # For now, keep fee simple/configurable.
    # Later, we can change this to SET or ADD if the workbook convention requires it.
    fee_behavior: ExcelWriteMode = ExcelWriteMode.SET

    # The mobile column should receive the summarized mobile net amount.
    mobile_column_value: str = "net_amt"


@dataclass(frozen=True)
class ExcelWriterPolicy:
    missing_workbook: MissingTargetPolicy = MissingTargetPolicy.WARN_AND_SKIP
    missing_sheet: MissingTargetPolicy = MissingTargetPolicy.WARN_AND_SKIP
    missing_header: MissingTargetPolicy = MissingTargetPolicy.WARN_AND_SKIP
    missing_date_row: MissingTargetPolicy = MissingTargetPolicy.WARN_AND_SKIP

    save_to_copy_by_default: bool = True
    create_missing_sheets: bool = False
    create_missing_date_rows: bool = False

    # For safety: do not blindly overwrite formulas unless explicitly allowed later.
    overwrite_formulas: bool = False


@dataclass(frozen=True)
class ExcelMapping:
    columns: ExcelColumnHeaders = ExcelColumnHeaders()
    valero_mobile_policy: ValeroMobileAdjustmentPolicy = ValeroMobileAdjustmentPolicy()
    writer_policy: ExcelWriterPolicy = ExcelWriterPolicy()

    header_scan_max_rows: int = 10

    # Files are expected like:
    # 2026 CC MONTECELLO VALERO.xlsx
    workbook_extension: str = ".xlsx"


EXCEL_MAPPING = ExcelMapping()


SUPPORTED_SUPPLIERS = {"CITGO", "VALERO", "SUNOCO"}


MONTH_SHEET_ALIASES: dict[int, tuple[str, ...]] = {
    1: ("JAN", "JANUARY"),
    2: ("FEB", "FEBRUARY"),
    3: ("MAR", "MARCH"),
    4: ("APR", "APRIL"),
    5: ("MAY",),
    6: ("JUN", "JUNE"),
    7: ("JUL", "JULY"),
    8: ("AUG", "AUGUST"),
    9: ("SEP", "SEPT", "SEPTEMBER"),
    10: ("OCT", "OCTOBER"),
    11: ("NOV", "NOVEMBER"),
    12: ("DEC", "DECEMBER"),
}


# Fill these as real workbook deviations are discovered.
# Key: (SUPPLIER, LOCATION_ID)
# Value: location name as it appears in workbook filename.
#
# Example:
# LOCATION_EXCEL_NAME_OVERRIDES = {
#     ("VALERO", "12345"): "9W",
#     ("VALERO", "67890"): "MONTECELLO",
# }
LOCATION_EXCEL_NAME_OVERRIDES: dict[tuple[str, str], str] = {}


# Use this only if the complete filename is known and does not follow convention.
# Key: (SUPPLIER, LOCATION_ID, YEAR)
# Value: exact workbook filename.
#
# Example:
# WORKBOOK_FILENAME_OVERRIDES = {
#     ("VALERO", "12345", 2026): "2026 CC 9W VALERO.xlsx",
# }
WORKBOOK_FILENAME_OVERRIDES: dict[tuple[str, str, int], str] = {}


LOCATION_DICTIONARIES: dict[str, dict[str, str]] = {
    "CITGO": CITGO_LOCATIONS,
    "VALERO": VALERO_LOCATIONS,
    "SUNOCO": SUNOCO_LOCATIONS,
}


def normalize_supplier(supplier: str) -> str:
    supplier_normalized = supplier.strip().upper()

    if supplier_normalized not in SUPPORTED_SUPPLIERS:
        raise ValueError(f"Unsupported supplier: {supplier}")

    return supplier_normalized


def normalize_excel_text(value: object) -> str:
    """
    Normalizes Excel names/headers for tolerant matching.

    Examples:
        " Gross AMT " -> "GROSS AMT"
        "MOBILE  PAY" -> "MOBILE PAY"
        "CC-Fee" -> "CC FEE"
    """
    if value is None:
        return ""

    text = str(value).strip().upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def strip_supplier_from_location_name(location_name: str, supplier: str) -> str:
    """
    Converts portal/config location names into likely workbook-location names.

    Examples:
        "Five Corners Valero" -> "FIVE CORNERS"
        "CENTRAL AVE SUNOCO" -> "CENTRAL AVE"
        "HAVERSTRAW" -> "HAVERSTRAW"
    """
    supplier = normalize_supplier(supplier)
    text = normalize_excel_text(location_name)

    supplier_tokens = {
        "CITGO": {"CITGO"},
        "VALERO": {"VALERO"},
        "SUNOCO": {"SUNOCO"},
    }[supplier]

    parts = [part for part in text.split() if part not in supplier_tokens]
    return " ".join(parts).strip()


def get_excel_location_name(
    supplier: str,
    location_id: str,
    location_name: str | None = None,
) -> str:
    supplier = normalize_supplier(supplier)
    location_id = str(location_id)

    override = LOCATION_EXCEL_NAME_OVERRIDES.get((supplier, location_id))
    if override:
        return normalize_excel_text(override)

    if location_name:
        return strip_supplier_from_location_name(location_name, supplier)

    known_location_name = LOCATION_DICTIONARIES.get(supplier, {}).get(location_id)
    if known_location_name:
        return strip_supplier_from_location_name(known_location_name, supplier)

    raise ValueError(
        f"No Excel location name mapping for supplier={supplier}, "
        f"location_id={location_id}"
    )


def get_workbook_filename(
    *,
    supplier: str,
    location_id: str,
    location_name: str | None,
    year: int,
) -> str:
    supplier = normalize_supplier(supplier)
    location_id = str(location_id)

    override = WORKBOOK_FILENAME_OVERRIDES.get((supplier, location_id, year))
    if override:
        return override

    excel_location_name = get_excel_location_name(
        supplier=supplier,
        location_id=location_id,
        location_name=location_name,
    )

    return f"{year} CC {excel_location_name} {supplier}{EXCEL_MAPPING.workbook_extension}"


def get_expected_workbook_path(
    *,
    workbook_root: Path,
    supplier: str,
    location_id: str,
    location_name: str | None,
    year: int,
) -> Path:
    filename = get_workbook_filename(
        supplier=supplier,
        location_id=location_id,
        location_name=location_name,
        year=year,
    )
    return workbook_root / filename


def get_month_sheet_candidates(target_date: date) -> tuple[str, ...]:
    month_aliases = MONTH_SHEET_ALIASES[target_date.month]
    return tuple(f"{month_name} {target_date.year}" for month_name in month_aliases)


def resolve_month_sheet_name(
    available_sheet_names: list[str] | tuple[str, ...],
    target_date: date,
) -> str | None:
    """
    Finds the actual workbook sheet name for a date.

    Supports both:
        JUN 2026
        JUNE 2026
    """
    normalized_available = {
        normalize_excel_text(sheet_name): sheet_name
        for sheet_name in available_sheet_names
    }

    for candidate in get_month_sheet_candidates(target_date):
        normalized_candidate = normalize_excel_text(candidate)
        if normalized_candidate in normalized_available:
            return normalized_available[normalized_candidate]

    return None

@dataclass(frozen=True)
class ExcelFeeValidationPolicy:
    enabled: bool = True
    tolerance: Decimal = Decimal("0.02")

    # Later, when workbook cells are opened, validate that CC Fee cells are formulas.
    require_formula_cell: bool = True