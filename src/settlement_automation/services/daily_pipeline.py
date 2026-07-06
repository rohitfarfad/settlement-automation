from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from config.settings import get_settings
from settlement_automation.models import ParsedReport
from settlement_automation.services.daily_run_summary import (
    DailyRunSummary,
    RunError,
    build_daily_run_summary,
)
from settlement_automation.services.notifications import (
    NotificationResult,
    handle_daily_notification,
)
from settlement_automation.services.report_processor import parse_report
from settlement_automation.services.validation import validate_report


SUPPORTED_SUPPLIERS = {"citgo", "valero", "sunoco"}
REPORT_SUFFIXES = {".txt", ".csv", ".json"}


@dataclass(frozen=True)
class SupplierReportInput:
    supplier: str
    report_path: Path | None


@dataclass
class DailyPipelineResult:
    summary: DailyRunSummary
    notification_result: NotificationResult | None = None


def normalize_supplier_name(value: str) -> str:
    return value.strip().lower()


def parse_supplier_list(values: list[str]) -> list[str]:
    suppliers = [normalize_supplier_name(value) for value in values]

    invalid = [supplier for supplier in suppliers if supplier not in SUPPORTED_SUPPLIERS]

    if invalid:
        raise ValueError(
            f"Unsupported supplier(s): {', '.join(invalid)}. "
            f"Supported suppliers: {', '.join(sorted(SUPPORTED_SUPPLIERS))}"
        )

    return suppliers


def find_downloaded_report(
    *,
    supplier: str,
    report_date: date,
    search_roots: list[Path] | None = None,
) -> Path | None:
    supplier = normalize_supplier_name(supplier)
    date_text = report_date.isoformat()

    if search_roots is None:
        search_roots = [
            Path("data/raw"),
            Path("data/incoming"),
            Path("data/tmp"),
            Path("data/processed"),
        ]

    candidates: list[Path] = []

    for root in search_roots:
        if not root.exists():
            continue

        for path in root.rglob("*"):
            if not path.is_file():
                continue

            if path.suffix.lower() not in REPORT_SUFFIXES:
                continue

            path_text = str(path).lower()

            if supplier not in path_text:
                continue

            if date_text not in path_text:
                continue

            candidates.append(path)

    if not candidates:
        return None

    candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return candidates[0]


@dataclass
class SupplierRunResult:
    supplier: str
    report_path: Path | None = None
    parsed_report: ParsedReport | None = None
    validation_result: object | None = None
    errors: list[RunError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def parse_and_validate_supplier_report(
    *,
    supplier: str,
    report_date: date,
    report_path: Path | None = None,
) -> SupplierRunResult:
    supplier = normalize_supplier_name(supplier)

    if report_path is None:
        report_path = find_downloaded_report(
            supplier=supplier,
            report_date=report_date,
        )

    result = SupplierRunResult(
        supplier=supplier.upper(),
        report_path=report_path,
    )

    if report_path is None:
        result.errors.append(
            RunError(
                stage="fetch",
                supplier=supplier.upper(),
                message=(
                    f"No downloaded report found for supplier={supplier.upper()} "
                    f"report_date={report_date}."
                ),
            )
        )
        return result

    try:
        parsed_report = parse_report(report_path)
        result.parsed_report = parsed_report
    except Exception as exc:
        result.errors.append(
            RunError(
                stage="parse",
                supplier=supplier.upper(),
                message=f"Failed to parse report: {report_path}",
                exception_type=type(exc).__name__,
            )
        )
        return result

    try:
        validation_result = validate_report(result.parsed_report)
        result.validation_result = validation_result

        for issue in getattr(validation_result, "issues", []) or []:
            level = getattr(issue, "level", "").upper()
            message = getattr(issue, "message", str(issue))

            if level == "ERROR":
                result.errors.append(
                    RunError(
                        stage="validation",
                        supplier=result.parsed_report.supplier,
                        message=message,
                    )
                )
            else:
                result.warnings.append(message)

    except Exception as exc:
        result.errors.append(
            RunError(
                stage="validation",
                supplier=result.parsed_report.supplier,
                message="Validation failed unexpectedly.",
                exception_type=type(exc).__name__,
            )
        )

    return result


def write_report_to_excel_if_requested(
    *,
    report: ParsedReport,
    dry_run: bool,
    write_originals: bool,
):
    settings = get_settings()

    # Adjust this import/function name to your current excel_writer public API.
    # The function should return ExcelWriteResult.
    from settlement_automation.services.excel_writer import write_parsed_report_to_excel

    return write_parsed_report_to_excel(
        report=report,
        workbook_root=settings.excel_workbook_root,
        output_root=settings.excel_output_dir,
        dry_run=dry_run,
        write_originals=write_originals,
    )


def run_daily_parse_write_notify(
    *,
    report_date: date,
    suppliers: list[str],
    write_excel: bool,
    excel_dry_run: bool,
    write_originals: bool,
    notify: bool,
) -> DailyPipelineResult:
    started_at = datetime.now()

    supplier_results: list[SupplierRunResult] = []
    parsed_reports: list[ParsedReport] = []
    validation_results: list[object] = []
    excel_results: list[object] = []
    errors: list[RunError] = []
    warnings: list[str] = []

    for supplier in parse_supplier_list(suppliers):
        supplier_result = parse_and_validate_supplier_report(
            supplier=supplier,
            report_date=report_date,
        )

        supplier_results.append(supplier_result)
        errors.extend(supplier_result.errors)
        warnings.extend(supplier_result.warnings)

        if supplier_result.parsed_report is None:
            continue

        parsed_reports.append(supplier_result.parsed_report)

        if supplier_result.validation_result is not None:
            validation_results.append(supplier_result.validation_result)

        if write_excel:
            try:
                excel_result = write_report_to_excel_if_requested(
                    report=supplier_result.parsed_report,
                    dry_run=excel_dry_run,
                    write_originals=write_originals,
                )
                excel_results.append(excel_result)

                for warning in getattr(excel_result, "warnings", []) or []:
                    warnings.append(str(warning))

            except Exception as exc:
                errors.append(
                    RunError(
                        stage="excel",
                        supplier=supplier_result.parsed_report.supplier,
                        message=(
                            "Excel writing failed for "
                            f"{supplier_result.parsed_report.supplier}."
                        ),
                        exception_type=type(exc).__name__,
                    )
                )

    finished_at = datetime.now()

    summary = build_daily_run_summary(
        report_date=report_date,
        run_date=date.today(),
        started_at=started_at,
        finished_at=finished_at,
        parsed_reports=parsed_reports,
        validation_results=validation_results,
        excel_results=excel_results,
        errors=errors,
        warnings=warnings,
    )

    notification_result = None

    if notify:
        notification_result = handle_daily_notification(summary)

    return DailyPipelineResult(
        summary=summary,
        notification_result=notification_result,
    )