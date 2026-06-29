from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from shutil import copy2
from typing import Any
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.utils.datetime import from_excel

from config.excel_mapping import (
    EXCEL_MAPPING,
    get_expected_workbook_path,
    normalize_supplier,
    resolve_month_sheet_name,
    normalize_excel_text
)
from settlement_automation.models import DailySettlementTotal, MobileAdjustment, ParsedReport
from settlement_automation.services.reconciliation import summarize_mobile_adjustments


@dataclass(frozen=True)
class ExcelFeeValidation:
    supplier: str
    location_id: str
    location_name: str
    business_date: date
    source: str
    gross_amt: Decimal
    net_amt: Decimal
    parsed_fees: Decimal
    calculated_fees: Decimal
    difference: Decimal
    is_valid: bool

@dataclass(frozen=True)
class ExcelTarget:
    supplier: str
    location_id: str
    location_name: str
    business_date: date
    workbook_path: Path
    sheet_name: str | None


@dataclass(frozen=True)
class ExcelPlannedValue:
    target: ExcelTarget
    field_name: str
    column_header: str
    value: Decimal
    source: str
    mode: str


@dataclass
class ExcelWritePlan:
    report_supplier: str
    report_date: date
    planned_values: list[ExcelPlannedValue] = field(default_factory=list)
    fee_validations: list[ExcelFeeValidation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings)

    @property
    def affected_workbooks(self) -> set[Path]:
        return {planned.target.workbook_path for planned in self.planned_values}

@dataclass
class ExcelWriteResult:
    dry_run: bool
    plan: ExcelWritePlan
    resolution: ExcelPlanResolution | None = None
    apply_result: ExcelApplyResult | None = None
    written_count: int = 0
    skipped_count: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExcelResolvedValue:
    planned_value: ExcelPlannedValue
    workbook_path: Path
    sheet_name: str
    header_row: int
    row_number: int
    column_number: int
    cell_ref: str
    current_value: object


@dataclass(frozen=True)
class ExcelFeeFormulaValidation:
    supplier: str
    location_id: str
    location_name: str
    business_date: date
    workbook_path: Path
    sheet_name: str
    cell_ref: str
    current_value: object
    is_formula: bool


@dataclass
class ExcelPlanResolution:
    resolved_values: list[ExcelResolvedValue] = field(default_factory=list)
    fee_formula_validations: list[ExcelFeeFormulaValidation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.warnings


@dataclass(frozen=True)
class ExcelAppliedChange:
    supplier: str
    location_id: str
    location_name: str
    business_date: date
    workbook_path: Path
    output_path: Path
    sheet_name: str
    cell_ref: str
    field_name: str
    column_header: str
    source: str
    mode: str
    old_value: object
    new_value: object
    status: str


@dataclass
class ExcelApplyResult:
    changes: list[ExcelAppliedChange] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def written_count(self) -> int:
        return sum(1 for change in self.changes if change.status == "written")

    @property
    def skipped_count(self) -> int:
        return sum(1 for change in self.changes if change.status.startswith("skipped"))


def _is_excel_temp_file(path: Path) -> bool:
    return path.name.startswith("~$")


def _resolve_existing_workbook_path(expected_path: Path) -> tuple[Path | None, list[str]]:
    warnings: list[str] = []

    if expected_path.exists() and not _is_excel_temp_file(expected_path):
        return expected_path, warnings

    workbook_dir = expected_path.parent
    if not workbook_dir.exists():
        warnings.append(f"Workbook directory does not exist: {workbook_dir}")
        return None, warnings

    expected_normalized = normalize_excel_text(expected_path.stem)

    candidates = [
        path
        for path in workbook_dir.glob("*.xlsx")
        if not _is_excel_temp_file(path)
    ]

    normalized_matches = [
        path
        for path in candidates
        if normalize_excel_text(path.stem) == expected_normalized
    ]

    if len(normalized_matches) == 1:
        warnings.append(
            f"Workbook exact path missing, but normalized match found: "
            f"expected={expected_path.name}, matched={normalized_matches[0].name}"
        )
        return normalized_matches[0], warnings

    scored_candidates = []
    for path in candidates:
        score = SequenceMatcher(
            None,
            expected_normalized,
            normalize_excel_text(path.stem),
        ).ratio()
        scored_candidates.append((score, path))

    scored_candidates.sort(reverse=True, key=lambda item: item[0])

    if scored_candidates and scored_candidates[0][0] >= 0.92:
        score, matched_path = scored_candidates[0]
        warnings.append(
            f"Workbook fuzzy match used: expected={expected_path.name}, "
            f"matched={matched_path.name}, score={score:.3f}. "
            f"Consider adding an override in config/excel_mapping.py."
        )
        return matched_path, warnings

    warnings.append(f"Workbook not found: {expected_path}")
    return None, warnings


def _coerce_excel_date(value: object) -> date | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, int | float):
        try:
            return from_excel(value).date()
        except Exception:
            return None

    if isinstance(value, str):
        text = value.strip()
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d-%b-%Y", "%d-%B-%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue

    return None


def _find_header_row_and_columns(
    ws,
    required_headers: set[str],
    *,
    max_rows: int,
) -> tuple[int, dict[str, int]] | None:
    normalized_required = {
        normalize_excel_text(header)
        for header in required_headers
    }

    for row_idx in range(1, min(ws.max_row, max_rows) + 1):
        header_map: dict[str, int] = {}

        for cell in ws[row_idx]:
            normalized_value = normalize_excel_text(cell.value)
            if normalized_value:
                header_map[normalized_value] = cell.column

        if normalized_required.issubset(set(header_map)):
            return row_idx, header_map

    return None


def _find_date_row(
    ws,
    *,
    date_column_number: int,
    header_row: int,
    target_date: date,
) -> int | None:
    for row_idx in range(header_row + 1, ws.max_row + 1):
        cell_value = ws.cell(row=row_idx, column=date_column_number).value
        if _coerce_excel_date(cell_value) == target_date:
            return row_idx

    return None

def _is_formula_value(value: object) -> bool:
    return isinstance(value, str) and value.startswith("=")

def _build_target_without_opening_workbook(
    *,
    workbook_root: Path,
    supplier: str,
    location_id: str,
    location_name: str,
    business_date: date,
) -> ExcelTarget:
    supplier = normalize_supplier(supplier)
    workbook_path = get_expected_workbook_path(
        workbook_root=workbook_root,
        supplier=supplier,
        location_id=location_id,
        location_name=location_name,
        year=business_date.year,
    )

    # Sheet name cannot be confirmed until the workbook is opened.
    # For now, use the first expected candidate as a placeholder.
    sheet_name = None

    return ExcelTarget(
        supplier=supplier,
        location_id=str(location_id),
        location_name=location_name,
        business_date=business_date,
        workbook_path=workbook_path,
        sheet_name=sheet_name,
    )


def _append_daily_total_values(
    *,
    plan: ExcelWritePlan,
    workbook_root: Path,
    row: DailySettlementTotal,
) -> None:
    columns = EXCEL_MAPPING.columns

    _validate_fee_math(
        plan=plan,
        supplier=row.supplier,
        location_id=row.location_id,
        location_name=row.location_name,
        business_date=row.date,
        gross_amt=row.gross_amt,
        net_amt=row.net_amt,
        parsed_fees=row.fees,
        source="daily_total",
    )

    target = _build_target_without_opening_workbook(
        workbook_root=workbook_root,
        supplier=row.supplier,
        location_id=row.location_id,
        location_name=row.location_name,
        business_date=row.date,
    )

    # Do not write CC Fee.
    # The workbook formula calculates it automatically.
    plan.planned_values.extend(
        [
            ExcelPlannedValue(
                target=target,
                field_name="gross_amt",
                column_header=columns.gross_amt,
                value=row.gross_amt,
                source="daily_total",
                mode="set",
            ),
            ExcelPlannedValue(
                target=target,
                field_name="net_amt",
                column_header=columns.net_amt,
                value=row.net_amt,
                source="daily_total",
                mode="set",
            ),
        ]
    )


def _append_valero_mobile_summary_values(
    *,
    plan: ExcelWritePlan,
    workbook_root: Path,
    row: MobileAdjustment,
) -> None:
    columns = EXCEL_MAPPING.columns

    _validate_fee_math(
        plan=plan,
        supplier=row.supplier,
        location_id=row.location_id,
        location_name=row.location_name,
        business_date=row.date,
        gross_amt=row.gross_amt,
        net_amt=row.net_amt,
        parsed_fees=row.fees,
        source="mobile_adjustment_summary",
    )

    target = _build_target_without_opening_workbook(
        workbook_root=workbook_root,
        supplier=row.supplier,
        location_id=row.location_id,
        location_name=row.location_name,
        business_date=row.date,
    )

    # Do not write CC Fee.
    # The workbook formula calculates it automatically.
    plan.planned_values.extend(
        [
            ExcelPlannedValue(
                target=target,
                field_name="gross_amt",
                column_header=columns.gross_amt,
                value=row.gross_amt,
                source="mobile_adjustment_summary",
                mode="add_to_base",
            ),
            ExcelPlannedValue(
                target=target,
                field_name="net_amt",
                column_header=columns.net_amt,
                value=row.net_amt,
                source="mobile_adjustment_summary",
                mode="add_to_base",
            ),
            ExcelPlannedValue(
                target=target,
                field_name="mobile_pay_added_to_gross_net",
                column_header=columns.mobile_pay,
                value=row.net_amt,
                source="mobile_adjustment_summary",
                mode="set",
            ),
        ]
    )


def build_excel_write_plan(
    *,
    report: ParsedReport,
    workbook_root: Path,
) -> ExcelWritePlan:
    supplier = normalize_supplier(report.supplier)

    plan = ExcelWritePlan(
        report_supplier=supplier,
        report_date=report.report_date,
    )

    for row in report.daily_totals:
        _append_daily_total_values(
            plan=plan,
            workbook_root=workbook_root,
            row=row,
        )

    if supplier == "VALERO":
        mobile_summary_rows = summarize_mobile_adjustments(report.mobile_adjustments)

        for row in mobile_summary_rows:
            _append_valero_mobile_summary_values(
                plan=plan,
                workbook_root=workbook_root,
                row=row,
            )
    elif report.mobile_adjustments:
        plan.warnings.append(
            f"Ignoring {len(report.mobile_adjustments)} mobile adjustment rows "
            f"for non-Valero supplier={supplier}."
        )

    return plan


def preview_excel_write_plan(plan: ExcelWritePlan) -> None:
    print("\n========== EXCEL WRITE PLAN ==========")
    print(f"report_supplier={plan.report_supplier}")
    print(f"report_date={plan.report_date}")
    print(f"planned_values={len(plan.planned_values)}")
    print(f"fee_validations={len(plan.fee_validations)}")
    print(f"affected_workbooks={len(plan.affected_workbooks)}")

    for workbook_path in sorted(plan.affected_workbooks):
        print(f"  workbook={workbook_path}")

    print("\n========== PLANNED CELL VALUES ==========")
    for planned in plan.planned_values:
        target = planned.target
        print(
            f"{target.supplier} | {target.location_id} | {target.location_name} | "
            f"{target.business_date} | {planned.column_header} | "
            f"{planned.source} | {planned.mode} | {planned.value} | "
            f"{target.workbook_path.name}"
        )

    print("\n========== FEE VALIDATION SUMMARY ==========")
    failed_fee_validations = [
        validation for validation in plan.fee_validations if not validation.is_valid
    ]
    print(f"total_fee_validations={len(plan.fee_validations)}")
    print(f"failed_fee_validations={len(failed_fee_validations)}")

    for validation in failed_fee_validations:
        print(
            "FEE WARNING: "
            f"{validation.supplier} | {validation.location_id} | "
            f"{validation.location_name} | {validation.business_date} | "
            f"{validation.source} | "
            f"gross={validation.gross_amt} | "
            f"net={validation.net_amt} | "
            f"calculated_fee={validation.calculated_fees} | "
            f"parsed_fee={validation.parsed_fees} | "
            f"difference={validation.difference}"
        )

    if plan.warnings:
        print("\n========== EXCEL PLAN WARNINGS ==========")
        for warning in plan.warnings:
            print(f"WARNING: {warning}")


def write_parsed_report_to_excel(
    *,
    report: ParsedReport,
    workbook_root: Path,
    output_root: Path,
    dry_run: bool = True,
) -> ExcelWriteResult:
    plan = build_excel_write_plan(
        report=report,
        workbook_root=workbook_root,
    )

    preview_excel_write_plan(plan)

    resolution = resolve_excel_write_plan_targets(plan)
    preview_excel_resolution(resolution)

    return ExcelWriteResult(
        dry_run=dry_run,
        plan=plan,
        written_count=0,
        skipped_count=len(resolution.warnings),
        warnings=plan.warnings.copy() + resolution.warnings.copy(),
    )

def _validate_fee_math(
    *,
    plan: ExcelWritePlan,
    supplier: str,
    location_id: str,
    location_name: str,
    business_date: date,
    gross_amt: Decimal,
    net_amt: Decimal,
    parsed_fees: Decimal,
    source: str,
) -> None:
    policy = EXCEL_MAPPING.fee_validation_policy

    if not policy.enabled:
        return

    calculated_fees = gross_amt - net_amt
    difference = calculated_fees - parsed_fees
    is_valid = abs(difference) <= policy.tolerance

    validation = ExcelFeeValidation(
        supplier=normalize_supplier(supplier),
        location_id=str(location_id),
        location_name=location_name,
        business_date=business_date,
        source=source,
        gross_amt=gross_amt,
        net_amt=net_amt,
        parsed_fees=parsed_fees,
        calculated_fees=calculated_fees,
        difference=difference,
        is_valid=is_valid,
    )

    plan.fee_validations.append(validation)

    if not is_valid:
        plan.warnings.append(
            "Fee validation mismatch: "
            f"{validation.supplier} {validation.location_id} "
            f"{validation.location_name} date={validation.business_date} "
            f"source={validation.source} "
            f"gross={validation.gross_amt} net={validation.net_amt} "
            f"calculated_fee={validation.calculated_fees} "
            f"parsed_fee={validation.parsed_fees} "
            f"difference={validation.difference}"
        )


def resolve_excel_write_plan_targets(plan: ExcelWritePlan) -> ExcelPlanResolution:
    resolution = ExcelPlanResolution()

    values_by_workbook: dict[Path, list[ExcelPlannedValue]] = defaultdict(list)

    for planned_value in plan.planned_values:
        values_by_workbook[planned_value.target.workbook_path].append(planned_value)

    for expected_workbook_path, planned_values in values_by_workbook.items():
        workbook_path, workbook_warnings = _resolve_existing_workbook_path(
            expected_workbook_path
        )
        resolution.warnings.extend(workbook_warnings)

        if workbook_path is None:
            continue

        try:
            wb = load_workbook(workbook_path, data_only=False)
        except Exception as exc:
            resolution.warnings.append(
                f"Could not open workbook: {workbook_path}. Error: {exc}"
            )
            continue

        values_by_date: dict[date, list[ExcelPlannedValue]] = defaultdict(list)
        for planned_value in planned_values:
            values_by_date[planned_value.target.business_date].append(planned_value)

        for business_date, date_values in values_by_date.items():
            sheet_name = resolve_month_sheet_name(wb.sheetnames, business_date)

            if sheet_name is None:
                resolution.warnings.append(
                    f"Missing month sheet for date={business_date} "
                    f"in workbook={workbook_path.name}. "
                    f"Available sheets={wb.sheetnames}"
                )
                continue

            ws = wb[sheet_name]

            required_headers = {
                EXCEL_MAPPING.columns.date,
                EXCEL_MAPPING.columns.gross_amt,
                EXCEL_MAPPING.columns.net_amt,
                EXCEL_MAPPING.columns.fees,
            }

            for planned_value in date_values:
                required_headers.add(planned_value.column_header)

            header_result = _find_header_row_and_columns(
                ws,
                required_headers,
                max_rows=EXCEL_MAPPING.header_scan_max_rows,
            )

            if header_result is None:
                resolution.warnings.append(
                    f"Could not find required headers in workbook={workbook_path.name}, "
                    f"sheet={sheet_name}, required={sorted(required_headers)}"
                )
                continue

            header_row, header_map = header_result
            date_column_number = header_map[normalize_excel_text(EXCEL_MAPPING.columns.date)]

            row_number = _find_date_row(
                ws,
                date_column_number=date_column_number,
                header_row=header_row,
                target_date=business_date,
            )

            if row_number is None:
                resolution.warnings.append(
                    f"Could not find date row: workbook={workbook_path.name}, "
                    f"sheet={sheet_name}, date={business_date}"
                )
                continue

            fee_column_number = header_map[normalize_excel_text(EXCEL_MAPPING.columns.fees)]
            fee_cell = ws.cell(row=row_number, column=fee_column_number)

            first_value = date_values[0]
            fee_validation = ExcelFeeFormulaValidation(
                supplier=first_value.target.supplier,
                location_id=first_value.target.location_id,
                location_name=first_value.target.location_name,
                business_date=business_date,
                workbook_path=workbook_path,
                sheet_name=sheet_name,
                cell_ref=fee_cell.coordinate,
                current_value=fee_cell.value,
                is_formula=_is_formula_value(fee_cell.value),
            )
            resolution.fee_formula_validations.append(fee_validation)

            if (
                EXCEL_MAPPING.fee_validation_policy.require_formula_cell
                and not fee_validation.is_formula
            ):
                resolution.warnings.append(
                    f"CC Fee cell is not a formula: workbook={workbook_path.name}, "
                    f"sheet={sheet_name}, date={business_date}, "
                    f"cell={fee_cell.coordinate}, value={fee_cell.value!r}"
                )

            for planned_value in date_values:
                normalized_header = normalize_excel_text(planned_value.column_header)

                if normalized_header not in header_map:
                    resolution.warnings.append(
                        f"Missing column header={planned_value.column_header} "
                        f"in workbook={workbook_path.name}, sheet={sheet_name}"
                    )
                    continue

                column_number = header_map[normalized_header]
                cell = ws.cell(row=row_number, column=column_number)
                cell_ref = f"{get_column_letter(column_number)}{row_number}"

                resolution.resolved_values.append(
                    ExcelResolvedValue(
                        planned_value=planned_value,
                        workbook_path=workbook_path,
                        sheet_name=sheet_name,
                        header_row=header_row,
                        row_number=row_number,
                        column_number=column_number,
                        cell_ref=cell_ref,
                        current_value=cell.value,
                    )
                )

    return resolution

def preview_excel_resolution(resolution: ExcelPlanResolution) -> None:
    print("\n========== EXCEL TARGET RESOLUTION ==========")
    print(f"resolved_values={len(resolution.resolved_values)}")
    print(f"fee_formula_validations={len(resolution.fee_formula_validations)}")
    print(f"warnings={len(resolution.warnings)}")

    print("\n========== RESOLVED CELL TARGETS ==========")
    for resolved in resolution.resolved_values:
        planned = resolved.planned_value
        target = planned.target
        print(
            f"{target.supplier} | {target.location_id} | {target.location_name} | "
            f"{target.business_date} | {resolved.workbook_path.name} | "
            f"{resolved.sheet_name}!{resolved.cell_ref} | "
            f"{planned.column_header} | {planned.source} | {planned.mode} | "
            f"current={resolved.current_value!r} | planned={planned.value}"
        )

    print("\n========== CC FEE FORMULA VALIDATION ==========")
    for validation in resolution.fee_formula_validations:
        status = "OK" if validation.is_formula else "WARNING"
        print(
            f"{status}: {validation.supplier} | {validation.location_id} | "
            f"{validation.location_name} | {validation.business_date} | "
            f"{validation.workbook_path.name} | "
            f"{validation.sheet_name}!{validation.cell_ref} | "
            f"value={validation.current_value!r}"
        )

    if resolution.warnings:
        print("\n========== EXCEL RESOLUTION WARNINGS ==========")
        for warning in resolution.warnings:
            print(f"WARNING: {warning}")