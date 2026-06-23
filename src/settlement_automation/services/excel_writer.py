from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from config.excel_mapping import (
    EXCEL_MAPPING,
    get_expected_workbook_path,
    normalize_supplier,
    resolve_month_sheet_name,
)
from settlement_automation.models import DailySettlementTotal, MobileAdjustment, ParsedReport
from settlement_automation.services.reconciliation import summarize_mobile_adjustments


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
    written_count: int = 0
    skipped_count: int = 0
    warnings: list[str] = field(default_factory=list)


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

    target = _build_target_without_opening_workbook(
        workbook_root=workbook_root,
        supplier=row.supplier,
        location_id=row.location_id,
        location_name=row.location_name,
        business_date=row.date,
    )

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
            ExcelPlannedValue(
                target=target,
                field_name="fees",
                column_header=columns.fees,
                value=row.fees,
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

    target = _build_target_without_opening_workbook(
        workbook_root=workbook_root,
        supplier=row.supplier,
        location_id=row.location_id,
        location_name=row.location_name,
        business_date=row.date,
    )

    # These are intentionally planned separately from daily totals.
    # Later the writer will combine daily base value + summarized mobile value
    # in an idempotent way.
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
    """
    Placeholder entrypoint.

    Next implementation step:
        - open affected workbooks
        - resolve actual sheet names
        - locate headers/date rows
        - apply values
        - save workbook copies

    For now this only builds and previews the plan.
    """
    plan = build_excel_write_plan(
        report=report,
        workbook_root=workbook_root,
    )

    preview_excel_write_plan(plan)

    return ExcelWriteResult(
        dry_run=dry_run,
        plan=plan,
        written_count=0,
        skipped_count=0,
        warnings=plan.warnings.copy(),
    )