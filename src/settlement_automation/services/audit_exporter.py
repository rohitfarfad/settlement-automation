import csv
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from settlement_automation.models import ParsedReport
from settlement_automation.services.validation import ValidationResult
from settlement_automation.services.reconciliation import (
    summarize_mobile_adjustments,
    summarize_valero_pay_plus_adjustments,
    summarize_valero_monthly_charges,
    summarize_sunoco_credit_card_discounts,
)


def clean_value(value):
    if isinstance(value, Decimal):
        return f"{value:.2f}"

    if isinstance(value, (date, datetime)):
        return value.isoformat()

    return value


def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        path.write_text("", encoding="utf-8")
        return

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def objects_to_rows(objects) -> list[dict]:
    rows = []

    for obj in objects:
        row = asdict(obj)
        row = {k: clean_value(v) for k, v in row.items()}
        rows.append(row)

    return rows


def validation_to_rows(result: ValidationResult) -> list[dict]:
    if not result.issues:
        return [{"level": "PASSED", "message": "No validation issues found."}]

    return [asdict(issue) for issue in result.issues]


def export_audit_files(
    report: ParsedReport,
    validation_result: ValidationResult,
    output_dir: str = "output/reports",
) -> list[Path]:
    output_path = Path(output_dir)

    prefix = f"{report.supplier}_{report.report_date.isoformat()}"

    files = {
        "daily_totals": output_path / f"{prefix}_daily_totals.csv",
        "mobile_detail": output_path / f"{prefix}_mobile_adjustments_detail.csv",
        "mobile_summary": output_path / f"{prefix}_mobile_adjustments_summary.csv",
        "valero_pay_plus_detail": output_path / f"{prefix}_valero_pay_plus_detail.csv",
        "valero_pay_plus_summary": output_path / f"{prefix}_valero_pay_plus_summary.csv",
        "validation": output_path / f"{prefix}_validation.csv",
        "valero_monthly_charges_detail": output_path / f"{prefix}_valero_monthly_charges_detail.csv",
        "valero_monthly_charges_summary": output_path / f"{prefix}_valero_monthly_charges_summary.csv",
        "sunoco_credit_card_discounts_detail": output_path / f"{prefix}_sunoco_credit_card_discounts_detail.csv",
        "sunoco_credit_card_discounts_summary": output_path / f"{prefix}_sunoco_credit_card_discounts_summary.csv",
    }

    write_csv(
        files["daily_totals"],
        objects_to_rows(report.daily_totals),
    )

    write_csv(
        files["mobile_detail"],
        objects_to_rows(report.mobile_adjustments),
    )

    write_csv(
        files["mobile_summary"],
        objects_to_rows(summarize_mobile_adjustments(report.mobile_adjustments)),
    )


    pay_plus_rows = getattr(report, "valero_pay_plus_adjustments", [])
    write_csv(
        files["valero_pay_plus_detail"],
        objects_to_rows(pay_plus_rows),
    )

    write_csv(
        files["valero_pay_plus_summary"],
        objects_to_rows(summarize_valero_pay_plus_adjustments(pay_plus_rows)),
    )

    monthly_charge_rows = getattr(report, "valero_monthly_charges", [])
    write_csv(
        files["valero_monthly_charges_detail"],
        objects_to_rows(monthly_charge_rows),
    )

    write_csv(
        files["valero_monthly_charges_summary"],
        objects_to_rows(summarize_valero_monthly_charges(monthly_charge_rows)),
    )

    sunoco_discount_rows = getattr(report, "sunoco_credit_card_discounts", [])

    write_csv(
        files["sunoco_credit_card_discounts_detail"],
        objects_to_rows(sunoco_discount_rows),
    )

    write_csv(
    files["sunoco_credit_card_discounts_summary"],
    objects_to_rows(summarize_sunoco_credit_card_discounts(sunoco_discount_rows)),

    )

    write_csv(
        files["validation"],
        validation_to_rows(validation_result),
    )


    return list(files.values())