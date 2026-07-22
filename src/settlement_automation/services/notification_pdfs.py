from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from settlement_automation.models import ParsedReport
from settlement_automation.services.daily_run_summary import DailyRunSummary
from settlement_automation.services.email_models import EmailAttachment
from settlement_automation.services.reconciliation import (
    get_mobile_adjustment_grand_total,
    summarize_mobile_adjustments,
)


# US standard Letter paper, landscape for wide settlement tables.
PDF_PAGE_SIZE = landscape(letter)
PDF_MARGIN = 0.50 * inch
PDF_CONTENT_WIDTH = PDF_PAGE_SIZE[0] - (2 * PDF_MARGIN)

# Printer-friendly grayscale palette.
PDF_HEADER_BG = colors.HexColor("#eeeeee")
PDF_GRID = colors.HexColor("#bdbdbd")
PDF_ROW_ALT = colors.HexColor("#fafafa")
PDF_TOTAL_BG = colors.HexColor("#e0e0e0")
PDF_TEXT = colors.HexColor("#000000")


@lru_cache(maxsize=1)
def _pdf_styles():
    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=18,
            alignment=TA_CENTER,
            textColor=PDF_TEXT,
            spaceAfter=8,
        )
    )

    styles.add(
        ParagraphStyle(
            name="ReportMeta",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            alignment=TA_LEFT,
            textColor=PDF_TEXT,
            spaceAfter=8,
        )
    )

    styles.add(
        ParagraphStyle(
            name="SectionHeading",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            alignment=TA_LEFT,
            textColor=PDF_TEXT,
            spaceBefore=8,
            spaceAfter=5,
        )
    )

    styles.add(
        ParagraphStyle(
            name="TableHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.2,
            leading=8.5,
            alignment=TA_LEFT,
            textColor=PDF_TEXT,
        )
    )

    styles.add(
        ParagraphStyle(
            name="TableCell",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=7.1,
            leading=8.4,
            alignment=TA_LEFT,
            textColor=PDF_TEXT,
        )
    )

    styles.add(
        ParagraphStyle(
            name="TableCellBold",
            parent=styles["TableCell"],
            fontName="Helvetica-Bold",
        )
    )

    styles.add(
        ParagraphStyle(
            name="TableNumber",
            parent=styles["TableCell"],
            alignment=TA_RIGHT,
        )
    )

    styles.add(
        ParagraphStyle(
            name="TableNumberBold",
            parent=styles["TableNumber"],
            fontName="Helvetica-Bold",
        )
    )

    return styles


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
        pagesize=PDF_PAGE_SIZE,
        leftMargin=PDF_MARGIN,
        rightMargin=PDF_MARGIN,
        topMargin=PDF_MARGIN,
        bottomMargin=PDF_MARGIN,
    )

    styles = _pdf_styles()
    story: list[Any] = []
    report_date = _summary_report_date(summary)

    story.append(
        Paragraph(
            "Credit Cards Daily Settlement Report",
            styles["ReportTitle"],
        )
    )
    story.append(
        Paragraph(
            f"<b>Supplier:</b> {xml_escape(str(report.supplier))} &nbsp;&nbsp; "
            f"<b>Report date:</b> {xml_escape(report_date.isoformat())} &nbsp;&nbsp; "
            f"<b>Generated:</b> {xml_escape(_format_datetime(datetime.now()))}",
            styles["ReportMeta"],
        )
    )
    story.append(Spacer(1, 8))

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
    story.append(Paragraph("Daily totals", styles["SectionHeading"]))

    if not rows_data:
        story.append(Paragraph("None", styles["ReportMeta"]))
        story.append(Spacer(1, 8))
        return

    table_rows = [["Date", "Location ID", "Location Name", "Gross", "Fees", "Net"]]

    is_valero = _is_supplier(report, "VALERO")
    is_citgo = _is_supplier(report, "CITGO")

    rows_to_render = rows_data

    if is_valero:
        rows_to_render = sorted(
            rows_data,
            key=lambda row: (
                row.date,
                str(row.location_id),
                str(row.location_name),
            ),
        )

    current_date = None
    current_date_rows = []

    for row in rows_to_render:
        if is_valero and current_date is not None and row.date != current_date:
            _append_daily_total_date_subtotal_row(
                table_rows=table_rows,
                total_date=current_date,
                rows=current_date_rows,
            )
            current_date_rows = []

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

        if is_valero:
            current_date = row.date
            current_date_rows.append(row)

    if is_valero and current_date_rows:
        _append_daily_total_date_subtotal_row(
            table_rows=table_rows,
            total_date=current_date,
            rows=current_date_rows,
        )

    has_total_row = not is_citgo

    if has_total_row:
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

    story.append(_make_table(table_rows, has_total_row=has_total_row))
    story.append(Spacer(1, 8))

def _append_daily_total_date_subtotal_row(
    *,
    table_rows: list[list[str]],
    total_date,
    rows,
) -> None:
    gross, fees, net = _sum_daily_totals(rows)

    table_rows.append(
        [
            f"TOTAL {total_date}",
            "",
            "",
            _format_money(gross),
            _format_money(fees),
            _format_money(net),
        ]
    )

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

    story.append(Paragraph("CITGO totals by date", styles["SectionHeading"]))

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
    story.append(Spacer(1, 8))


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

    story.append(
        Paragraph("Sunoco credit card discount summary", styles["SectionHeading"])
    )

    summarized_rows = _summarize_sunoco_credit_card_discounts(rows_data)
    table_rows = [["Date", "Location ID", "Location Name", "Count", "Amount", "Source"]]

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
    total_amount = sum((row["amount"] for row in summarized_rows), Decimal("0"))
    table_rows.append(
        ["GRAND TOTAL", "", "", str(total_count), _format_money(total_amount), ""]
    )

    story.append(_make_table(table_rows))
    story.append(Spacer(1, 8))


def _append_mobile_adjustment_summary(
    story: list[Any],
    styles,
    report: ParsedReport,
) -> None:
    rows_data = getattr(report, "mobile_adjustments", []) or []

    if not rows_data:
        return

    story.append(
        Paragraph("Backdated mobile adjustment summary", styles["SectionHeading"])
    )

    table_rows = [["Date", "Location ID", "Location Name", "Gross", "Fees", "Net"]]

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
    story.append(Spacer(1, 8))


def _append_valero_pay_plus_summary(
    story: list[Any],
    styles,
    report: ParsedReport,
) -> None:
    rows_data = getattr(report, "valero_pay_plus_adjustments", []) or []

    if not rows_data:
        return

    story.append(Paragraph("Valero Pay+ adjustment summary", styles["SectionHeading"]))

    summarized_rows = _summarize_valero_pay_plus(rows_data)
    table_rows = [["Date", "Location ID", "Location Name", "Count", "Amount", "Sources"]]

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
    total_amount = sum((row["amount"] for row in summarized_rows), Decimal("0"))
    table_rows.append(
        ["GRAND TOTAL", "", "", str(total_count), _format_money(total_amount), ""]
    )

    story.append(_make_table(table_rows))
    story.append(Spacer(1, 8))


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

    story.append(Paragraph("Valero Pay+ totals by date", styles["SectionHeading"]))

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
    total_amount = sum((row["amount"] for row in summarized_rows), Decimal("0"))
    table_rows.append(["GRAND TOTAL", str(total_count), _format_money(total_amount), ""])

    story.append(_make_table(table_rows))
    story.append(Spacer(1, 8))


def _append_valero_monthly_charges(
    story: list[Any],
    styles,
    report: ParsedReport,
) -> None:
    rows_data = getattr(report, "valero_monthly_charges", []) or []

    if not rows_data:
        return

    story.append(Paragraph("Valero monthly charge summary", styles["SectionHeading"]))

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
    total_amount = sum((row["amount"] for row in summarized_rows), Decimal("0"))
    table_rows.append(["GRAND TOTAL", "", str(total_count), _format_money(total_amount)])

    story.append(_make_table(table_rows))
    story.append(Spacer(1, 8))


def _append_unclassified_adjustments(
    story: list[Any],
    styles,
    report: ParsedReport,
) -> None:
    rows_data = getattr(report, "unclassified_adjustments", []) or []

    if not rows_data:
        return

    story.append(Paragraph("Unclassified adjustments", styles["SectionHeading"]))

    table_rows = [["Report date", "Location ID", "Location Name", "Amount", "Description"]]

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

    story.append(_make_table(table_rows, has_total_row=False))
    story.append(Spacer(1, 8))


def _make_table(
    rows: list[list[str]],
    *,
    has_total_row: bool = True,
) -> Table:
    if not rows:
        rows = [[""]]

    headers = [str(value) for value in rows[0]]
    numeric_columns = _numeric_column_indexes(headers)
    col_widths = _column_widths(headers)
    total_row_indexes = _total_row_indexes(rows, has_total_row=has_total_row)

    table = Table(
        _paragraph_rows(
            rows,
            numeric_columns,
            total_row_indexes=total_row_indexes,
        ),
        colWidths=col_widths,
        repeatRows=1,
        hAlign="LEFT",
    )

    style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), PDF_HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), PDF_TEXT),
        ("GRID", (0, 0), (-1, -1), 0.35, PDF_GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PDF_ROW_ALT]),
    ]

    for column_index in numeric_columns:
        style_commands.append(
            ("ALIGN", (column_index, 0), (column_index, -1), "RIGHT")
        )

    for row_index in sorted(total_row_indexes):
        style_commands.extend(
            [
                ("BACKGROUND", (0, row_index), (-1, row_index), PDF_TOTAL_BG),
                (
                    "LINEABOVE",
                    (0, row_index),
                    (-1, row_index),
                    0.6,
                    colors.HexColor("#9ca3af"),
                ),
            ]
        )

    table.setStyle(TableStyle(style_commands))
    return table


def _paragraph_rows(
    rows: list[list[str]],
    numeric_columns: set[int],
    *,
    total_row_indexes: set[int],
) -> list[list[Paragraph]]:
    styles = _pdf_styles()
    result: list[list[Paragraph]] = []

    for row_index, row in enumerate(rows):
        output_row = []

        for column_index, value in enumerate(row):
            is_header = row_index == 0
            is_total = row_index in total_row_indexes
            is_numeric = column_index in numeric_columns

            if is_header:
                style = styles["TableHeader"]
            elif is_total and is_numeric:
                style = styles["TableNumberBold"]
            elif is_total:
                style = styles["TableCellBold"]
            elif is_numeric:
                style = styles["TableNumber"]
            else:
                style = styles["TableCell"]

            output_row.append(
                Paragraph(
                    xml_escape(str(value or "")),
                    style,
                )
            )

        result.append(output_row)

    return result
def _total_row_indexes(
    rows: list[list[str]],
    *,
    has_total_row: bool,
) -> set[int]:
    if not has_total_row or len(rows) <= 1:
        return set()

    indexes = {
        row_index
        for row_index, row in enumerate(rows[1:], start=1)
        if _is_total_row(row)
    }

    if not indexes:
        indexes.add(len(rows) - 1)

    return indexes


def _is_total_row(row: list[str]) -> bool:
    if not row:
        return False

    label = str(row[0] or "").strip().upper()

    return label == "GRAND TOTAL" or label.startswith("TOTAL ")

def _numeric_column_indexes(headers: list[str]) -> set[int]:
    numeric_names = {
        "Rows",
        "Count",
        "Gross",
        "Fees",
        "Net",
        "Amount",
        "Discount Amount",
    }

    return {
        index
        for index, header in enumerate(headers)
        if header.strip() in numeric_names
    }



def _column_widths(headers: list[str]) -> list[float]:
    weights = []

    for header in headers:
        normalized = header.strip().lower()

        if normalized in {"date", "report date"}:
            weights.append(0.95)
        elif normalized == "location id":
            weights.append(0.95)
        elif normalized == "location name":
            weights.append(2.6)
        elif normalized in {"gross", "net", "amount", "discount amount"}:
            weights.append(1.05)
        elif normalized == "fees":
            weights.append(0.9)
        elif normalized in {"rows", "count"}:
            weights.append(0.65)
        elif normalized in {"source", "sources"}:
            weights.append(1.35)
        elif normalized == "description":
            weights.append(2.7)
        else:
            weights.append(1.0)

    total_weight = sum(weights) or 1

    return [PDF_CONTENT_WIDTH * (weight / total_weight) for weight in weights]


def _summary_report_date(summary: DailyRunSummary):
    report_date = getattr(summary, "report_date", None)
    if report_date is not None:
        return report_date

    return getattr(summary, "business_date")


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
