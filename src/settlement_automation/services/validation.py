from dataclasses import dataclass
from decimal import Decimal

from settlement_automation.models import ParsedReport


@dataclass
class ValidationIssue:
    level: str  # "ERROR" or "WARNING"
    message: str


@dataclass
class ValidationResult:
    is_valid: bool
    issues: list[ValidationIssue]


def _money_matches(left: Decimal, right: Decimal) -> bool:
    return abs(left - right) <= Decimal("0.01")


def validate_report(report: ParsedReport) -> ValidationResult:
    issues = []

    if not report.daily_totals:
        issues.append(
            ValidationIssue(
                level="ERROR",
                message="No daily totals found in report.",
            )
        )

    seen_daily_keys = set()

    for row in report.daily_totals:
        key = (row.supplier, row.location_id, row.date)

        if key in seen_daily_keys:
            issues.append(
                ValidationIssue(
                    level="ERROR",
                    message=f"Duplicate daily total found for {row.supplier} "
                            f"{row.location_id} {row.date}.",
                )
            )

        seen_daily_keys.add(key)

        if row.location_name == "UNKNOWN":
            issues.append(
                ValidationIssue(
                    level="WARNING",
                    message=f"Unknown location name for {row.supplier} "
                            f"location {row.location_id}.",
                )
            )

        expected_net = row.gross_amt - row.fees

        if not _money_matches(expected_net, row.net_amt):
            issues.append(
                ValidationIssue(
                    level="ERROR",
                    message=f"Net mismatch for {row.supplier} {row.location_id} "
                            f"{row.date}: gross {row.gross_amt} - fees {row.fees} "
                            f"!= net {row.net_amt}.",
                )
            )

    for row in report.mobile_adjustments:
        if row.location_name == "UNKNOWN":
            issues.append(
                ValidationIssue(
                    level="WARNING",
                    message=f"Unknown location name for mobile adjustment "
                            f"{row.supplier} {row.location_id}.",
                )
            )

        expected_net = row.gross_amt - row.fees

        if not _money_matches(expected_net, row.net_amt):
            issues.append(
                ValidationIssue(
                    level="ERROR",
                    message=f"Mobile adjustment net mismatch for {row.supplier} "
                            f"{row.location_id} {row.date} {row.source_code}: "
                            f"gross {row.gross_amt} - fees {row.fees} "
                            f"!= net {row.net_amt}.",
                )
            )
    for row in getattr(report, "valero_pay_plus_adjustments", []):
        if row.location_name == "UNKNOWN":
            issues.append(
                ValidationIssue(
                    level="WARNING",
                    message=f"Unknown location name for Valero Pay+ adjustment "
                            f"{row.supplier} {row.location_id} {row.date}.",
                )
            )

        if row.amount < Decimal("0.00"):
            issues.append(
                ValidationIssue(
                    level="WARNING",
                    message=f"Negative Valero Pay+ adjustment for {row.supplier} "
                            f"{row.location_id} {row.date}: {row.amount}.",
                )
            )

    for row in getattr(report, "valero_monthly_charges", []):
        if row.location_name == "UNKNOWN":
            issues.append(
                ValidationIssue(
                    level="WARNING",
                    message=f"Unknown location name for Valero monthly charge "
                            f"{row.supplier} {row.location_id} {row.date}.",
                )
            )

        if row.amount < Decimal("0.00"):
            issues.append(
                ValidationIssue(
                    level="WARNING",
                    message=f"Negative parsed Valero monthly charge for "
                            f"{row.supplier} {row.location_id} {row.date}: "
                            f"{row.amount}.",
                )
            )

    for row in getattr(report, "sunoco_credit_card_discounts", []):
        if row.location_name == "UNKNOWN":
            issues.append(
                ValidationIssue(
                    level="WARNING",
                    message=f"Unknown location name for SUNOCO credit card discount "
                            f"{row.supplier} {row.location_id} {row.date}.",
                )
            )

        if row.amount < Decimal("0.00"):
            issues.append(
                ValidationIssue(
                    level="WARNING",
                    message=f"Negative SUNOCO credit card discount for "
                            f"{row.supplier} {row.location_id} {row.date}: "
                            f"{row.amount}.",
                )
            )

    has_errors = any(issue.level == "ERROR" for issue in issues)

    return ValidationResult(
        is_valid=not has_errors,
        issues=issues,
    )