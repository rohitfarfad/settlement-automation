from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from settlement_automation.models import ParsedReport


AnomalyLevel = Literal["INFO", "WARNING", "ERROR"]


@dataclass(frozen=True)
class AnomalyIssue:
    level: AnomalyLevel
    code: str
    supplier: str | None
    message: str
    location_id: str | None = None
    location_name: str | None = None
    transaction_date: date | None = None
    amount: Decimal | None = None
    raw_line: str | None = None


def detect_unclassified_adjustments(report: ParsedReport) -> list[AnomalyIssue]:
    issues = []

    for adjustment in report.unclassified_adjustments:
        issues.append(
            AnomalyIssue(
                level="WARNING",
                code="UNCLASSIFIED_ADJUSTMENT",
                supplier=report.supplier,
                location_id=adjustment.location_id,
                location_name=adjustment.location_name,
                transaction_date=adjustment.report_date,
                amount=adjustment.amount,
                raw_line=adjustment.raw_line,
                message=(
                    f"{report.supplier} has an unclassified adjustment "
                    f"for {adjustment.location_name or adjustment.location_id}."
                ),
            )
        )

    return issues


def detect_previous_month_after_10th(
    report: ParsedReport,
    run_date: date,
) -> list[AnomalyIssue]:
    issues = []

    if run_date.day <= 10:
        return issues

    current_month = (run_date.year, run_date.month)

    for row in report.daily_totals:
        row_month = (row.date.year, row.date.month)

        if row_month < current_month:
            issues.append(
                AnomalyIssue(
                    level="WARNING",
                    code="PREVIOUS_MONTH_AFTER_10TH",
                    supplier=report.supplier,
                    location_id=row.location_id,
                    location_name=row.location_name,
                    transaction_date=row.date,
                    amount=row.gross_amt,
                    message=(
                        f"{report.supplier} has previous-month settlement data "
                        f"for {row.location_name} dated {row.date}, "
                        f"but the run date is {run_date}."
                    ),
                )
            )

    return issues

def detect_report_anomalies(
    report: ParsedReport,
    run_date: date,
) -> list[AnomalyIssue]:
    issues = []

    issues.extend(detect_unclassified_adjustments(report))
    issues.extend(detect_previous_month_after_10th(report, run_date))

    return issues
