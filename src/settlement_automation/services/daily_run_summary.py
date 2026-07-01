from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

from settlement_automation.models import ParsedReport
from settlement_automation.services.anomaly_detector import (
    AnomalyIssue,
    detect_report_anomalies,
)


RunStage = Literal[
    "fetch",
    "parse",
    "validation",
    "excel",
    "notification",
    "unknown",
]


@dataclass(frozen=True)
class RunError:
    stage: RunStage
    message: str
    supplier: str | None = None
    location_id: str | None = None
    location_name: str | None = None
    exception_type: str | None = None


@dataclass(frozen=True)
class DailyRunSummary:
    business_date: date
    run_date: date
    started_at: datetime
    finished_at: datetime | None = None

    fetch_results: list[Any] = field(default_factory=list)
    parsed_reports: list[ParsedReport] = field(default_factory=list)
    validation_results: list[Any] = field(default_factory=list)
    excel_results: list[Any] = field(default_factory=list)

    anomalies: list[AnomalyIssue] = field(default_factory=list)
    errors: list[RunError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings or self.anomalies)

    @property
    def supplier_names(self) -> list[str]:
        names = {report.supplier for report in self.parsed_reports}
        return sorted(names)

    @property
    def daily_total_count(self) -> int:
        return sum(len(report.daily_totals) for report in self.parsed_reports)

    @property
    def mobile_adjustment_count(self) -> int:
        return sum(len(report.mobile_adjustments) for report in self.parsed_reports)

    @property
    def valero_pay_plus_count(self) -> int:
        return sum(
            len(report.valero_pay_plus_adjustments)
            for report in self.parsed_reports
        )

    @property
    def valero_monthly_charge_count(self) -> int:
        return sum(
            len(report.valero_monthly_charges)
            for report in self.parsed_reports
        )

    @property
    def unclassified_adjustment_count(self) -> int:
        return sum(
            len(report.unclassified_adjustments)
            for report in self.parsed_reports
        )

    @property
    def warning_count(self) -> int:
        return len(self.warnings) + len(self.anomalies)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def excel_written_count(self) -> int:
        return sum(
            getattr(result, "written_count", 0)
            for result in self.excel_results
        )

    @property
    def excel_skipped_count(self) -> int:
        return sum(
            getattr(result, "skipped_count", 0)
            for result in self.excel_results
        )

    @property
    def excel_warning_count(self) -> int:
        return sum(
            len(getattr(result, "warnings", []) or [])
            for result in self.excel_results
        )

def build_daily_run_summary(
    *,
    business_date: date,
    started_at: datetime,
    finished_at: datetime | None = None,
    run_date: date | None = None,
    fetch_results: list[Any] | None = None,
    parsed_reports: list[ParsedReport] | None = None,
    validation_results: list[Any] | None = None,
    excel_results: list[Any] | None = None,
    errors: list[RunError] | None = None,
    warnings: list[str] | None = None,
) -> DailyRunSummary:
    parsed_reports = parsed_reports or []

    effective_run_date = run_date or date.today()

    anomalies: list[AnomalyIssue] = []

    for report in parsed_reports:
        anomalies.extend(
            detect_report_anomalies(
                report=report,
                run_date=effective_run_date,
            )
        )

    return DailyRunSummary(
        business_date=business_date,
        run_date=effective_run_date,
        started_at=started_at,
        finished_at=finished_at,
        fetch_results=fetch_results or [],
        parsed_reports=parsed_reports,
        validation_results=validation_results or [],
        excel_results=excel_results or [],
        anomalies=anomalies,
        errors=errors or [],
        warnings=warnings or [],
    )