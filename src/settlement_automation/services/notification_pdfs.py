from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from settlement_automation.models import ParsedReport
from settlement_automation.services.daily_run_summary import DailyRunSummary
from settlement_automation.services.email_models import EmailAttachment
from settlement_automation.services.reconciliation import (
    get_mobile_adjustment_grand_total,
    summarize_mobile_adjustments,
)


def build_supplier_pdf_attachments(
    *,
    summary: DailyRunSummary,
    output_dir: Path,
) -> tuple[list[EmailAttachment], list[Path]]:
    output_dir.mkdir(parents=True, exist_ok=True)

    attachments: list[EmailAttachment] = []
    paths: list[Path] = []

    report_date = _summary_report_date(summary)

    for report in summary.parsed_reports:
        supplier = str(report.supplier).strip().lower()
        pdf_name = f"{report_date.isoformat()}_{supplier}_summary.pdf"
        pdf_path = output_dir / pdf_name

        write_supplier_pdf(
            summary=summary,
            report=report,
            output_path=pdf_path,
        )

        attachments.append(
            EmailAttachment(
                name=pdf_name,
                content_type="application/pdf",
                content_bytes=pdf_path.read_bytes(),
            )
        )
        paths.append(pdf_path)

    return attachments, paths


def write_supplier_pdf(
    *,
    summary: DailyRunSummary,
    report: ParsedReport,
    output_path: Path,
) -> None:
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=landscape(letter),
        leftMargin=0.35 * inch,
        rightMargin=0.35 * inch,
        topMargin=0.35 * inch,
        bottomMargin=0.35 * inch,
    )

    styles = getSampleStyleSheet()
    story: list[Any] = []

    report_date = _summary_report_date(summary)

    story.append(Paragraph("Credit Cards Daily Settlement Report", styles["Title"]))
    story.append(
        Paragraph(
            f"Supplier: {report.supplier} &nbsp;&nbsp; "
            f"Report date: {report_date.isoformat()} &nbsp;&nbsp; "
            f"Generated: {_format_datetime(datetime.now())}",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 12))

    _append_daily_totals(story, styles, report)
    _append_sunoco_credit_card_discounts(story, styles, report)
    _append_citgo_totals_by_date(story, styles, report)
    _append_mobile_adjustment_summary(story, styles, report)
    _append_valero_pay_plus_summary(story, styles, report)
    _append_valero_pay_plus_totals_by_date(story, styles, report)
    _append_valero_monthly_charges(story, styles, report)
    _append_unclassified_adjustments(story, styles, report)

    doc.build(story)


def _append_daily_totals(story: list[Any], styles, report: ParsedReport) -> None:
    rows_data = getattr(report, "daily_totals", []) or []

    story.append(Paragraph("Daily totals", styles["Heading2"]))

    if not rows_data:
        story.append(Paragraph("None", styles["Normal"]))
        story.append(Spacer(1, 10))
        return

    table_rows = [
        ["Date", "Location ID", "Location Name", "Gross", "Fees", "Net"]
    ]

    for row in rows_data:
        table_rows.append(
            [
                str(row.date),
                str(row.location_id),
                str(row.location_name),
                _format_money(row.gross_amt),
                _format_money(row.fees),
                _format_money(row.net_amt),
            ]
        )

    if not _is_supplier(report, "CITGO"):
        gross, fees, net = _sum_daily_totals(rows_data)
        table_rows.append(
            [
                "GRAND TOTAL",
                "",
                "",
                _format_money(gross),
                _format_money(fees),
                _format_money(net),
            ]
        )

    story.append(_make_table(table_rows))
    story.append(Spacer(1, 12))


def _append_citgo_totals_by_date(
    story: list[Any],
    styles,
    report: ParsedReport,
) -> None:
    if not _is_supplier(report, "CITGO"):
        return

    rows_data = getattr(report, "daily_totals", []) or []

    if not rows_data:
        return

    story.append(Paragraph("CITGO totals by date", styles["Heading2"]))

    table_rows = [["Date", "Rows", "Gross", "Fees", "Net"]]

    for row in _summarize_daily_totals_by_date(rows_data):
        table_rows.append(
            [
                str(row["date"]),
                str(row["count"]),
                _format_money(row["gross_amt"]),
                _format_money(row["fees"]),
                _format_money(row["net_amt"]),
            ]
        )

    gross, fees, net = _sum_daily_totals(rows_data)

    table_rows.append(
        [
            "GRAND TOTAL",
            str(len(rows_data)),
            _format_money(gross),
            _format_money(fees),
            _format_money(net),
        ]
    )

    story.append(_make_table(table_rows))
    story.append(Spacer(1, 12))


def _append_sunoco_credit_card_discounts(
    story: list[Any],
    styles,
    report: ParsedReport,
) -> None:
    if not _is_supplier(report, "SUNOCO"):
        return

    rows_data = getattr(report, "sunoco_credit_card_discounts", []) or []

    if not rows_data:
        return

    story.append(Paragraph("Sunoco credit card discount summary", styles["Heading2"]))

    summarized_rows = _summarize_sunoco_credit_card_discounts(rows_data)
    table_rows = [
        ["Date", "Location ID", "Location Name", "Count", "Amount", "Source"]
    ]

    for row in summarized_rows:
        sources = ", ".join(sorted(row["sources"]))

        table_rows.append(
            [
                str(row["date"]),
                str(row["location_id"]),
                str(row["location_name"]),
                str(row["count"]),
                _format_money(row["amount"]),
                sources,
            ]
        )

    total_count = sum(row["count"] for row in summarized_rows)
    total_amount = sum(
        (row["amount"] for row in summarized_rows),
        Decimal("0"),
    )

    table_rows.append(
        [
            "GRAND TOTAL",
            "",
            "",
            str(total_count),
            _format_money(total_amount),
            "",
        ]
    )

    story.append(_make_table(table_rows))
    story.append(Spacer(1, 12))


def _append_mobile_adjustment_summary(
    story: list[Any],
    styles,
    report: ParsedReport,
) -> None:
    rows_data = getattr(report, "mobile_adjustments", []) or []

    if not rows_data:
        return

    story.append(Paragraph("Backdated mobile adjustment summary", styles["Heading2"]))

    table_rows = [
        ["Date", "Location ID", "Location Name", "Gross", "Fees", "Net"]
    ]

    for row in sorted(
        summarize_mobile_adjustments(rows_data),
        key=lambda item: (item.date, item.location_id),
    ):
        table_rows.append(
            [
                str(row.date),
                str(row.location_id),
                str(row.location_name),
                _format_money(row.gross_amt),
                _format_money(row.fees),
                _format_money(row.net_amt),
            ]
        )

    gross, fees, net = get_mobile_adjustment_grand_total(rows_data)

    table_rows.append(
        [
            "GRAND TOTAL",
            "",
            "",
            _format_money(gross),
            _format_money(fees),
            _format_money(net),
        ]
    )

    story.append(_make_table(table_rows))
    story.append(Spacer(1, 12))


def _append_valero_pay_plus_summary(
    story: list[Any],
    styles,
    report: ParsedReport,
) -> None:
    rows_data = getattr(report, "valero_pay_plus_adjustments", []) or []

    if not rows_data:
        return

    story.append(Paragraph("Valero Pay+ adjustment summary", styles["Heading2"]))

    summarized_rows = _summarize_valero_pay_plus(rows_data)
    table_rows = [
        ["Date", "Location ID", "Location Name", "Count", "Amount", "Sources"]
    ]

    for row in summarized_rows:
        sources = ", ".join(sorted(row["sources"]))

        table_rows.append(
            [
                str(row["date"]),
                str(row["location_id"]),
                str(row["location_name"]),
                str(row["count"]),
                _format_money(row["amount"]),
                sources,
            ]
        )

    total_count = sum(row["count"] for row in summarized_rows)
    total_amount = sum(
        (row["amount"] for row in summarized_rows),
        Decimal("0"),
    )

    table_rows.append(
        [
            "GRAND TOTAL",
            "",
            "",
            str(total_count),
            _format_money(total_amount),
            "",
        ]
    )

    story.append(_make_table(table_rows))
    story.append(Spacer(1, 12))


def _append_valero_pay_plus_totals_by_date(
    story: list[Any],
    styles,
    report: ParsedReport,
) -> None:
    rows_data = getattr(report, "valero_pay_plus_adjustments", []) or []

    if not rows_data:
        return

    summarized_rows = _summarize_valero_pay_plus_by_date(rows_data)

    if len(summarized_rows) <= 1:
        return

    story.append(Paragraph("Valero Pay+ totals by date", styles["Heading2"]))

    table_rows = [["Date", "Rows", "Amount", "Sources"]]

    for row in summarized_rows:
        sources = ", ".join(sorted(row["sources"]))

        table_rows.append(
            [
                str(row["date"]),
                str(row["count"]),
                _format_money(row["amount"]),
                sources,
            ]
        )

    total_count = sum(row["count"] for row in summarized_rows)
    total_amount = sum(
        (row["amount"] for row in summarized_rows),
        Decimal("0"),
    )

    table_rows.append(
        [
            "GRAND TOTAL",
            str(total_count),
            _format_money(total_amount),
            "",
        ]
    )

    story.append(_make_table(table_rows))
    story.append(Spacer(1, 12))


def _append_valero_monthly_charges(
    story: list[Any],
    styles,
    report: ParsedReport,
) -> None:
    rows_data = getattr(report, "valero_monthly_charges", []) or []

    if not rows_data:
        return

    story.append(Paragraph("Valero monthly charge summary", styles["Heading2"]))

    summarized_rows = _summarize_valero_monthly_charges(rows_data)

    table_rows = [["Location ID", "Location Name", "Count", "Amount"]]

    for row in summarized_rows:
        table_rows.append(
            [
                str(row["location_id"]),
                str(row["location_name"]),
                str(row["count"]),
                _format_money(row["amount"]),
            ]
        )

    total_count = sum(row["count"] for row in summarized_rows)
    total_amount = sum(
        (row["amount"] for row in summarized_rows),
        Decimal("0"),
    )

    table_rows.append(
        [
            "GRAND TOTAL",
            "",
            str(total_count),
            _format_money(total_amount),
        ]
    )

    story.append(_make_table(table_rows))
    story.append(Spacer(1, 12))


def _append_unclassified_adjustments(
    story: list[Any],
    styles,
    report: ParsedReport,
) -> None:
    rows_data = getattr(report, "unclassified_adjustments", []) or []

    if not rows_data:
        return

    story.append(Paragraph("Unclassified adjustments", styles["Heading2"]))

    table_rows = [
        ["Report date", "Location ID", "Location Name", "Amount", "Description"]
    ]

    for row in rows_data:
        table_rows.append(
            [
                str(row.report_date),
                str(row.location_id),
                str(row.location_name),
                _format_money(row.amount),
                str(row.description),
            ]
        )

    story.append(_make_table(table_rows))
    story.append(Spacer(1, 12))


def _make_table(rows: list[list[str]]) -> Table:
    table = Table(rows, repeatRows=1)

    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f7")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111827")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cfd8e3")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e5e7eb")),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ]
        )
    )

    return table


def _summary_report_date(summary: DailyRunSummary):
    return getattr(summary, "report_date", getattr(summary, "business_date"))


def _is_supplier(report: ParsedReport, supplier: str) -> bool:
    return str(getattr(report, "supplier", "")).strip().upper() == supplier.upper()


def _format_money(value: Decimal | None) -> str:
    if value is None:
        return "-"

    value = Decimal(value)

    if value < 0:
        return f"-${abs(value):,.2f}"

    return f"${value:,.2f}"


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "-"

    return value.isoformat(sep=" ", timespec="seconds")


def _sum_daily_totals(rows) -> tuple[Decimal, Decimal, Decimal]:
    gross = Decimal("0")
    fees = Decimal("0")
    net = Decimal("0")

    for row in rows:
        gross += row.gross_amt or Decimal("0")
        fees += row.fees or Decimal("0")
        net += row.net_amt or Decimal("0")

    return gross, fees, net


def _summarize_daily_totals_by_date(rows):
    summary = {}

    for row in rows:
        key = row.date

        if key not in summary:
            summary[key] = {
                "date": row.date,
                "count": 0,
                "gross_amt": Decimal("0"),
                "fees": Decimal("0"),
                "net_amt": Decimal("0"),
            }

        summary[key]["count"] += 1
        summary[key]["gross_amt"] += row.gross_amt or Decimal("0")
        summary[key]["fees"] += row.fees or Decimal("0")
        summary[key]["net_amt"] += row.net_amt or Decimal("0")

    return sorted(summary.values(), key=lambda item: item["date"])


def _summarize_valero_pay_plus(rows):
    summary = {}

    for row in rows:
        key = (row.date, row.location_id, row.location_name)

        if key not in summary:
            summary[key] = {
                "date": row.date,
                "location_id": row.location_id,
                "location_name": row.location_name,
                "count": 0,
                "amount": Decimal("0"),
                "sources": set(),
            }

        summary[key]["count"] += 1

        if row.amount is not None:
            summary[key]["amount"] += row.amount

        if row.source_code:
            summary[key]["sources"].add(str(row.source_code))

    return sorted(summary.values(), key=lambda item: (item["date"], item["location_id"]))


def _summarize_valero_pay_plus_by_date(rows):
    summary = {}

    for row in rows:
        key = row.date

        if key not in summary:
            summary[key] = {
                "date": row.date,
                "count": 0,
                "amount": Decimal("0"),
                "sources": set(),
            }

        summary[key]["count"] += 1

        if row.amount is not None:
            summary[key]["amount"] += row.amount

        if row.source_code:
            summary[key]["sources"].add(str(row.source_code))

    return sorted(summary.values(), key=lambda item: item["date"])


def _summarize_valero_monthly_charges(rows):
    summary = {}

    for row in rows:
        key = row.location_id

        if key not in summary:
            summary[key] = {
                "location_id": row.location_id,
                "location_name": row.location_name,
                "count": 0,
                "amount": Decimal("0"),
            }

        summary[key]["count"] += 1

        if row.amount is not None:
            summary[key]["amount"] += row.amount

    return sorted(summary.values(), key=lambda item: item["location_id"])


def _summarize_sunoco_credit_card_discounts(rows):
    summary = {}

    for row in rows:
        key = (row.date, row.location_id, row.location_name)

        if key not in summary:
            summary[key] = {
                "date": row.date,
                "location_id": row.location_id,
                "location_name": row.location_name,
                "count": 0,
                "amount": Decimal("0"),
                "sources": set(),
            }

        summary[key]["count"] += 1

        if row.amount is not None:
            summary[key]["amount"] += row.amount

        source_field = getattr(row, "source_field", None)

        if source_field:
            summary[key]["sources"].add(str(source_field))

    return sorted(summary.values(), key=lambda item: (item["date"], item["location_id"]))