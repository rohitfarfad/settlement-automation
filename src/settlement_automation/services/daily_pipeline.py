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
from config.supplier_accounts import get_supplier_account
from settlement_automation.connectors.download_manager import DownloadManager
from settlement_automation.ingestion.dtn_group_fetch import (
    fetch_dtn_reports_for_supplier_group,
)
from settlement_automation.ingestion.fetch_reports import (
    FetchResult,
    fetch_reports_for_account,
)
from settlement_automation.ingestion.supplier_selection import group_suppliers_by_portal
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

def fetch_reports_for_daily_run(
    *,
    report_date: date,
    suppliers: list[str],
) -> tuple[list[FetchResult], list[RunError]]:
    """
    Fetch reports for the daily run.

    Note:
    Existing fetch APIs still call the date `business_date`.
    For the daily cron pipeline, we pass report_date into that argument.
    User-facing/email wording should continue to say report date.
    """
    settings = get_settings()
    download_manager = DownloadManager(settings=settings)

    fetch_results: list[FetchResult] = []
    errors: list[RunError] = []

    supplier_groups = group_suppliers_by_portal(suppliers)

    for group in supplier_groups:
        try:
            if group.portal_name == "dtn":
                # CITGO + VALERO share one DTN login/session.
                # This function also works when only one DTN supplier is selected.
                dtn_results = fetch_dtn_reports_for_supplier_group(
                    supplier_names=group.supplier_names,
                    business_date=report_date,
                    download_manager=download_manager,
                    settings=settings,
                    remove_downloaded_files=True,
                )

                for supplier_name in group.supplier_names:
                    fetch_result = dtn_results.get(supplier_name)

                    if fetch_result is None:
                        errors.append(
                            RunError(
                                stage="fetch",
                                supplier=supplier_name.upper(),
                                message=(
                                    "DTN fetch did not return a result for "
                                    f"supplier={supplier_name.upper()} "
                                    f"report_date={report_date}."
                                ),
                            )
                        )
                        continue

                    fetch_results.append(fetch_result)

                continue

            # Non-DTN suppliers, currently SUNOCO.
            for supplier_name in group.supplier_names:
                account = get_supplier_account(supplier_name)

                fetch_result = fetch_reports_for_account(
                    account=account,
                    business_date=report_date,
                    download_manager=download_manager,
                    remove_downloaded_files=True,
                    raise_on_error=False,
                )

                fetch_results.append(fetch_result)

        except Exception as exc:
            # Group-level unexpected failure.
            # Normal supplier failures should usually be captured inside FetchResult,
            # but this prevents the whole cron run from crashing.
            for supplier_name in group.supplier_names:
                errors.append(
                    RunError(
                        stage="fetch",
                        supplier=supplier_name.upper(),
                        message=(
                            f"Unexpected {group.portal_name.upper()} fetch failure "
                            f"for supplier={supplier_name.upper()} "
                            f"report_date={report_date}."
                        ),
                        exception_type=type(exc).__name__,
                    )
                )

    return fetch_results, errors


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

def run_daily_fetch_parse_write_notify(
    *,
    report_date: date,
    suppliers: list[str],
    write_excel: bool,
    excel_dry_run: bool,
    write_originals: bool,
    notify: bool,
) -> DailyPipelineResult:
    """
    Full daily cron/UI pipeline:

    fetch -> parse -> validate -> write Excel -> notify

    This is intended for unattended daily runs.
    The older run_daily_parse_write_notify() is still useful for manually
    reprocessing already-downloaded reports.
    """
    started_at = datetime.now()

    parsed_reports: list[ParsedReport] = []
    validation_results: list[object] = []
    excel_results: list[object] = []
    errors: list[RunError] = []
    warnings: list[str] = []

    normalized_suppliers = parse_supplier_list(suppliers)

    fetch_results, fetch_orchestration_errors = fetch_reports_for_daily_run(
        report_date=report_date,
        suppliers=normalized_suppliers,
    )
    errors.extend(fetch_orchestration_errors)

    for fetch_result in fetch_results:
        supplier = normalize_supplier_name(fetch_result.supplier_name)
        supplier_display = supplier.upper()

        if not fetch_result.succeeded:
            errors.append(
                RunError(
                    stage="fetch",
                    supplier=supplier_display,
                    message=(
                        fetch_result.error_message
                        or (
                            f"Fetch failed for supplier={supplier_display} "
                            f"report_date={report_date}."
                        )
                    ),
                )
            )
            continue

        raw_paths = fetch_result.raw_paths

        if not raw_paths:
            errors.append(
                RunError(
                    stage="fetch",
                    supplier=supplier_display,
                    message=(
                        f"Fetch succeeded but no raw report was stored for "
                        f"supplier={supplier_display} report_date={report_date}."
                    ),
                )
            )
            continue

        for raw_path in raw_paths:
            supplier_result = parse_and_validate_supplier_report(
                supplier=supplier,
                report_date=report_date,
                report_path=raw_path,
            )

            errors.extend(supplier_result.errors)
            warnings.extend(supplier_result.warnings)

            if supplier_result.parsed_report is None:
                continue

            parsed_reports.append(supplier_result.parsed_report)

            if supplier_result.validation_result is not None:
                validation_results.append(supplier_result.validation_result)

            has_parse_or_validation_errors = any(
                error.stage in {"parse", "validation"}
                for error in supplier_result.errors
            )

            if has_parse_or_validation_errors:
                # Accuracy rule:
                # if parsing/validation found a blocking problem,
                # do not write that report to Excel.
                continue

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
        fetch_results=fetch_results,
        parsed_reports=parsed_reports,
        validation_results=validation_results,
        excel_results=excel_results,
        errors=errors,
        warnings=warnings,
    )

    notification_result = None
    if notify:
        try:
            notification_result = handle_daily_notification(summary)
        except Exception as exc:
            errors.append(
                RunError(
                    stage="notification",
                    message="Daily notification failed unexpectedly.",
                    exception_type=type(exc).__name__,
                )
            )

            # Rebuild summary so the notification error appears in the returned
            # result object and in console output.
            summary = build_daily_run_summary(
                report_date=report_date,
                run_date=date.today(),
                started_at=started_at,
                finished_at=datetime.now(),
                fetch_results=fetch_results,
                parsed_reports=parsed_reports,
                validation_results=validation_results,
                excel_results=excel_results,
                errors=errors,
                warnings=warnings,
            )

    return DailyPipelineResult(
        summary=summary,
        notification_result=notification_result,
    )