from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from html import escape
from typing import Any

from settlement_automation.models import ParsedReport
from settlement_automation.services.daily_run_summary import DailyRunSummary

from pathlib import Path
from typing import Literal
from settlement_automation.services.email_senders import (
    EmailRecipients,
    GraphEmailConfig,
    GraphEmailSender,
    parse_recipient_list,
)
from settlement_automation.services.email_models import DailyEmailContent

NotificationMode = Literal["off", "dry_run", "test", "live"]
NotificationProvider = Literal["graph", "smtp"]


@dataclass(frozen=True)
class NotificationConfig:
    enabled: bool
    mode: NotificationMode
    provider: NotificationProvider
    output_dir: Path

    email_to: str = ""
    email_cc: str = ""
    email_bcc: str = ""
    email_test_to: str = ""

    graph_tenant_id: str = ""
    graph_client_id: str = ""
    graph_client_secret: str = ""
    graph_sender_email: str = ""

    @property
    def is_off(self) -> bool:
        return not self.enabled or self.mode == "off"

    @property
    def should_write_preview(self) -> bool:
        return self.enabled and self.mode in {"dry_run", "test", "live"}

    @property
    def should_send(self) -> bool:
        return self.enabled and self.mode in {"test", "live"}

@dataclass(frozen=True)
class NotificationResult:
    enabled: bool
    mode: str
    provider: str
    sent: bool
    preview_text_path: Path | None = None
    preview_html_path: Path | None = None
    error_message: str | None = None

def build_daily_email(summary: DailyRunSummary) -> DailyEmailContent:
    subject = _build_subject(summary)
    plain_text = _build_plain_text(summary)
    html = _build_html(summary)

    return DailyEmailContent(
        subject=subject,
        plain_text=plain_text,
        html=html,
    )


def load_notification_config() -> NotificationConfig:
    from config.settings import get_settings

    settings = get_settings()

    mode = settings.notification_email_mode
    provider = settings.notification_email_provider

    if mode not in {"off", "dry_run", "test", "live"}:
        raise ValueError(
            "NOTIFICATION_EMAIL_MODE must be one of: "
            "off, dry_run, test, live"
        )

    if provider not in {"graph", "smtp"}:
        raise ValueError(
            "NOTIFICATION_EMAIL_PROVIDER must be one of: graph, smtp"
        )

    if not settings.notification_email_enabled:
        mode = "off"

    return NotificationConfig(
        enabled=settings.notification_email_enabled,
        mode=mode,
        provider=provider,
        output_dir=settings.notification_output_dir,
        email_to=settings.notification_email_to,
        email_cc=settings.notification_email_cc,
        email_bcc=settings.notification_email_bcc,
        email_test_to=settings.notification_email_test_to,
        graph_tenant_id=settings.graph_tenant_id,
        graph_client_id=settings.graph_client_id,
        graph_client_secret=settings.graph_client_secret,
        graph_sender_email=settings.graph_sender_email,
    )

def build_email_recipients(config: NotificationConfig) -> EmailRecipients:
    if config.mode == "test":
        return EmailRecipients(
            to=parse_recipient_list(config.email_test_to),
            cc=[],
            bcc=[],
        )

    return EmailRecipients(
        to=parse_recipient_list(config.email_to),
        cc=parse_recipient_list(config.email_cc),
        bcc=parse_recipient_list(config.email_bcc),
    )

def _build_subject(summary: DailyRunSummary) -> str:
    status = "OK"

    if summary.has_errors:
        status = "ERROR"
    elif summary.has_warnings:
        status = "WARNING"

    return (
        f"[{status}] Prestige Settlement Daily Report "
        f"- Business Date {summary.business_date.isoformat()}"
    )


def _build_plain_text(summary: DailyRunSummary) -> str:
    lines: list[str] = []

    lines.append("Prestige Settlement Daily Report")
    lines.append("=" * 40)
    lines.append(f"Business date: {summary.business_date.isoformat()}")
    lines.append(f"Run date: {summary.run_date.isoformat()}")
    lines.append(f"Started at: {_format_datetime(summary.started_at)}")

    if summary.finished_at:
        lines.append(f"Finished at: {_format_datetime(summary.finished_at)}")

    lines.append("")
    lines.extend(_build_plain_status_section(summary))
    lines.append("")
    lines.extend(_build_plain_fetch_section(summary))
    lines.append("")
    lines.extend(_build_plain_parsed_data_section(summary))
    lines.append("")
    lines.extend(_build_plain_excel_section(summary))
    lines.append("")
    lines.extend(_build_plain_warning_section(summary))
    lines.append("")
    lines.extend(_build_plain_error_section(summary))

    return "\n".join(lines).rstrip() + "\n"


def _build_html(summary: DailyRunSummary) -> str:
    status_label = "Success"

    if summary.has_errors:
        status_label = "Errors found"
    elif summary.has_warnings:
        status_label = "Warnings found"

    sections = [
        f"<h1>Prestige Settlement Daily Report</h1>",
        "<table>",
        _html_row("Business date", summary.business_date.isoformat()),
        _html_row("Run date", summary.run_date.isoformat()),
        _html_row("Started at", _format_datetime(summary.started_at)),
        _html_row("Finished at", _format_datetime(summary.finished_at) if summary.finished_at else "-"),
        _html_row("Status", status_label),
        "</table>",
        _build_html_status_section(summary),
        _build_html_fetch_section(summary),
        _build_html_parsed_data_section(summary),
        _build_html_excel_section(summary),
        _build_html_warning_section(summary),
        _build_html_error_section(summary),
    ]

    return "\n".join(sections)


def _build_plain_status_section(summary: DailyRunSummary) -> list[str]:
    return [
        "Run summary",
        "-" * 40,
        f"Suppliers parsed: {', '.join(summary.supplier_names) if summary.supplier_names else '-'}",
        f"Daily totals: {summary.daily_total_count}",
        f"Mobile adjustments: {summary.mobile_adjustment_count}",
        f"Valero Pay+ adjustments: {summary.valero_pay_plus_count}",
        f"Valero monthly charges: {summary.valero_monthly_charge_count}",
        f"Unclassified adjustments: {summary.unclassified_adjustment_count}",
        f"Warnings: {summary.warning_count}",
        f"Errors: {summary.error_count}",
    ]


def _build_plain_fetch_section(summary: DailyRunSummary) -> list[str]:
    lines = [
        "Fetch results",
        "-" * 40,
    ]

    if not summary.fetch_results:
        lines.append("- No fetch results available.")
        return lines

    for result in summary.fetch_results:
        supplier_name = getattr(result, "supplier_name", "-")
        portal_name = getattr(result, "portal_name", "-")
        status = getattr(result, "status", "-")
        error_message = getattr(result, "error_message", None)

        lines.append(f"- {supplier_name} / {portal_name}: {status}")

        raw_paths = getattr(result, "raw_paths", [])
        for raw_path in raw_paths:
            lines.append(f"  raw: {raw_path}")

        if error_message:
            lines.append(f"  error: {error_message}")

    return lines


def _build_plain_parsed_data_section(summary: DailyRunSummary) -> list[str]:
    lines = [
        "Data parsed for sheet entry",
        "-" * 40,
    ]

    if not summary.parsed_reports:
        lines.append("- No parsed reports available.")
        return lines

    for report in summary.parsed_reports:
        lines.append(f"{report.supplier}")
        lines.extend(_format_plain_daily_totals(report))
        lines.extend(_format_plain_mobile_adjustments(report))
        lines.extend(_format_plain_valero_pay_plus(report))
        lines.extend(_format_plain_valero_monthly_charges(report))
        lines.extend(_format_plain_unclassified_adjustments(report))
        lines.append("")

    return lines


def _build_plain_excel_section(summary: DailyRunSummary) -> list[str]:
    lines = [
        "Excel write summary",
        "-" * 40,
        f"Written cells: {getattr(summary, 'excel_written_count', 0)}",
        f"Skipped cells: {getattr(summary, 'excel_skipped_count', 0)}",
        f"Excel warnings: {getattr(summary, 'excel_warning_count', 0)}",
    ]

    if not summary.excel_results:
        lines.append("- No Excel write results available.")
        return lines

    for result in summary.excel_results:
        written_count = getattr(result, "written_count", 0)
        skipped_count = getattr(result, "skipped_count", 0)
        dry_run = getattr(result, "dry_run", None)
        write_originals = getattr(result, "write_originals", None)

        plan = getattr(result, "plan", None)
        report_supplier = getattr(plan, "report_supplier", "-")
        report_date = getattr(plan, "report_date", "-")

        lines.append(
            f"- {report_supplier} {report_date}: "
            f"written={written_count}, skipped={skipped_count}, "
            f"dry_run={dry_run}, write_originals={write_originals}"
        )

        for warning in getattr(result, "warnings", []) or []:
            lines.append(f"  warning: {warning}")

        apply_result = getattr(result, "apply_result", None)
        changes = getattr(apply_result, "changes", []) if apply_result else []

        for change in changes[:20]:
            lines.append(
                "  "
                f"{change.supplier} | {change.location_name} | "
                f"{change.business_date} | {change.sheet_name}!{change.cell_ref} | "
                f"{change.field_name} | {change.status} | "
                f"{_format_value(change.old_value)} -> {_format_value(change.new_value)}"
            )

        if len(changes) > 20:
            lines.append(f"  ... {len(changes) - 20} more Excel changes omitted")

    return lines


def _build_plain_warning_section(summary: DailyRunSummary) -> list[str]:
    lines = [
        "Warnings",
        "-" * 40,
    ]

    has_any = False

    for warning in summary.warnings:
        has_any = True
        lines.append(f"- {warning}")

    for anomaly in summary.anomalies:
        has_any = True
        lines.append(
            f"- [{anomaly.code}] {anomaly.message}"
            f"{_format_optional_detail('supplier', anomaly.supplier)}"
            f"{_format_optional_detail('location', anomaly.location_name or anomaly.location_id)}"
            f"{_format_optional_detail('date', anomaly.transaction_date)}"
            f"{_format_optional_detail('amount', _format_money(anomaly.amount) if anomaly.amount is not None else None)}"
        )

        raw_line = getattr(anomaly, "raw_line", None)
        if raw_line:
            lines.append(f"  raw: {raw_line}")

    if not has_any:
        lines.append("- No warnings.")

    return lines


def _build_plain_error_section(summary: DailyRunSummary) -> list[str]:
    lines = [
        "Errors",
        "-" * 40,
    ]

    if not summary.errors:
        lines.append("- No errors.")
        return lines

    for error in summary.errors:
        lines.append(
            f"- [{error.stage}] {error.message}"
            f"{_format_optional_detail('supplier', error.supplier)}"
            f"{_format_optional_detail('location', error.location_name or error.location_id)}"
            f"{_format_optional_detail('exception', error.exception_type)}"
        )

    return lines


def _format_plain_daily_totals(report: ParsedReport) -> list[str]:
    if not report.daily_totals:
        return ["- Daily totals: none"]

    lines = ["- Daily totals:"]

    for row in report.daily_totals:
        lines.append(
            "  "
            f"{row.date} | {row.location_name} ({row.location_id}) | "
            f"Gross {_format_money(row.gross_amt)} | "
            f"Fees {_format_money(row.fees)} | "
            f"Net {_format_money(row.net_amt)}"
        )

    return lines


def _format_plain_mobile_adjustments(report: ParsedReport) -> list[str]:
    if not report.mobile_adjustments:
        return []

    lines = ["- Mobile adjustments:"]

    for row in report.mobile_adjustments:
        lines.append(
            "  "
            f"{row.date} | {row.location_name} ({row.location_id}) | "
            f"Gross {_format_money(row.gross_amt)} | "
            f"Fees {_format_money(row.fees)} | "
            f"Net {_format_money(row.net_amt)}"
            f"{_format_optional_detail('source', row.source_code)}"
        )

    return lines


def _format_plain_valero_pay_plus(report: ParsedReport) -> list[str]:
    rows = getattr(report, "valero_pay_plus_adjustments", []) or []

    if not rows:
        return []

    lines = ["- Valero Pay+ adjustments:"]

    for row in rows:
        lines.append(
            "  "
            f"{row.date} | {row.location_name} ({row.location_id}) | "
            f"Amount {_format_money(row.amount)}"
            f"{_format_optional_detail('source', row.source_code)}"
        )

    return lines


def _format_plain_valero_monthly_charges(report: ParsedReport) -> list[str]:
    rows = getattr(report, "valero_monthly_charges", []) or []

    if not rows:
        return []

    lines = ["- Valero monthly charges:"]

    for row in rows:
        lines.append(
            "  "
            f"{row.date} | {row.location_name} ({row.location_id}) | "
            f"Amount {_format_money(row.amount)} | "
            f"{row.description}"
        )

    return lines


def _format_plain_unclassified_adjustments(report: ParsedReport) -> list[str]:
    rows = getattr(report, "unclassified_adjustments", []) or []

    if not rows:
        return []

    lines = ["- Unclassified adjustments:"]

    for row in rows:
        lines.append(
            "  "
            f"{row.report_date} | {row.location_name} ({row.location_id}) | "
            f"Amount {_format_money(row.amount) if row.amount is not None else '-'} | "
            f"{row.description}"
        )

    return lines


def _build_html_status_section(summary: DailyRunSummary) -> str:
    return "\n".join(
        [
            "<h2>Run summary</h2>",
            "<table>",
            _html_row("Suppliers parsed", ", ".join(summary.supplier_names) if summary.supplier_names else "-"),
            _html_row("Daily totals", summary.daily_total_count),
            _html_row("Mobile adjustments", summary.mobile_adjustment_count),
            _html_row("Valero Pay+ adjustments", summary.valero_pay_plus_count),
            _html_row("Valero monthly charges", summary.valero_monthly_charge_count),
            _html_row("Unclassified adjustments", summary.unclassified_adjustment_count),
            _html_row("Warnings", summary.warning_count),
            _html_row("Errors", summary.error_count),
            "</table>",
        ]
    )


def _build_html_fetch_section(summary: DailyRunSummary) -> str:
    if not summary.fetch_results:
        return "<h2>Fetch results</h2><p>No fetch results available.</p>"

    rows = []

    for result in summary.fetch_results:
        raw_paths = getattr(result, "raw_paths", [])
        raw_paths_text = "<br>".join(escape(str(path)) for path in raw_paths) or "-"

        rows.append(
            "<tr>"
            f"<td>{escape(str(getattr(result, 'supplier_name', '-')))}</td>"
            f"<td>{escape(str(getattr(result, 'portal_name', '-')))}</td>"
            f"<td>{escape(str(getattr(result, 'status', '-')))}</td>"
            f"<td>{raw_paths_text}</td>"
            f"<td>{escape(str(getattr(result, 'error_message', '') or ''))}</td>"
            "</tr>"
        )

    return "\n".join(
        [
            "<h2>Fetch results</h2>",
            "<table>",
            "<tr><th>Supplier</th><th>Portal</th><th>Status</th><th>Raw files</th><th>Error</th></tr>",
            *rows,
            "</table>",
        ]
    )


def _build_html_parsed_data_section(summary: DailyRunSummary) -> str:
    if not summary.parsed_reports:
        return "<h2>Data parsed for sheet entry</h2><p>No parsed reports available.</p>"

    parts = ["<h2>Data parsed for sheet entry</h2>"]

    for report in summary.parsed_reports:
        parts.append(f"<h3>{escape(report.supplier)}</h3>")
        parts.append(_build_html_daily_totals_table(report))
        parts.append(_build_html_mobile_adjustments_table(report))
        parts.append(_build_html_valero_pay_plus_table(report))
        parts.append(_build_html_valero_monthly_charges_table(report))
        parts.append(_build_html_unclassified_adjustments_table(report))

    return "\n".join(part for part in parts if part)


def _build_html_excel_section(summary: DailyRunSummary) -> str:
    rows = []

    for result in summary.excel_results:
        plan = getattr(result, "plan", None)

        rows.append(
            "<tr>"
            f"<td>{escape(str(getattr(plan, 'report_supplier', '-')))}</td>"
            f"<td>{escape(str(getattr(plan, 'report_date', '-')))}</td>"
            f"<td>{escape(str(getattr(result, 'written_count', 0)))}</td>"
            f"<td>{escape(str(getattr(result, 'skipped_count', 0)))}</td>"
            f"<td>{escape(str(getattr(result, 'dry_run', '-')))}</td>"
            f"<td>{escape(str(getattr(result, 'write_originals', '-')))}</td>"
            "</tr>"
        )

    if not rows:
        rows.append("<tr><td colspan='6'>No Excel write results available.</td></tr>")

    return "\n".join(
        [
            "<h2>Excel write summary</h2>",
            "<table>",
            "<tr><th>Supplier</th><th>Report date</th><th>Written</th><th>Skipped</th><th>Dry run</th><th>Write originals</th></tr>",
            *rows,
            "</table>",
        ]
    )


def _build_html_warning_section(summary: DailyRunSummary) -> str:
    items = []

    for warning in summary.warnings:
        items.append(f"<li>{escape(warning)}</li>")

    for anomaly in summary.anomalies:
        text = (
            f"[{anomaly.code}] {anomaly.message}"
            f"{_format_optional_detail('supplier', anomaly.supplier)}"
            f"{_format_optional_detail('location', anomaly.location_name or anomaly.location_id)}"
            f"{_format_optional_detail('date', anomaly.transaction_date)}"
            f"{_format_optional_detail('amount', _format_money(anomaly.amount) if anomaly.amount is not None else None)}"
        )
        items.append(f"<li>{escape(text)}</li>")

    if not items:
        items.append("<li>No warnings.</li>")

    return "\n".join(["<h2>Warnings</h2>", "<ul>", *items, "</ul>"])


def _build_html_error_section(summary: DailyRunSummary) -> str:
    items = []

    for error in summary.errors:
        text = (
            f"[{error.stage}] {error.message}"
            f"{_format_optional_detail('supplier', error.supplier)}"
            f"{_format_optional_detail('location', error.location_name or error.location_id)}"
            f"{_format_optional_detail('exception', error.exception_type)}"
        )
        items.append(f"<li>{escape(text)}</li>")

    if not items:
        items.append("<li>No errors.</li>")

    return "\n".join(["<h2>Errors</h2>", "<ul>", *items, "</ul>"])


def _build_html_daily_totals_table(report: ParsedReport) -> str:
    if not report.daily_totals:
        return "<p>Daily totals: none</p>"

    rows = [
        "<tr><th>Date</th><th>Location</th><th>Gross</th><th>Fees</th><th>Net</th></tr>"
    ]

    for row in report.daily_totals:
        rows.append(
            "<tr>"
            f"<td>{escape(str(row.date))}</td>"
            f"<td>{escape(row.location_name)} ({escape(row.location_id)})</td>"
            f"<td>{escape(_format_money(row.gross_amt))}</td>"
            f"<td>{escape(_format_money(row.fees))}</td>"
            f"<td>{escape(_format_money(row.net_amt))}</td>"
            "</tr>"
        )

    return "\n".join(["<h4>Daily totals</h4>", "<table>", *rows, "</table>"])


def _build_html_mobile_adjustments_table(report: ParsedReport) -> str:
    if not report.mobile_adjustments:
        return ""

    rows = [
        "<tr><th>Date</th><th>Location</th><th>Gross</th><th>Fees</th><th>Net</th><th>Source</th></tr>"
    ]

    for row in report.mobile_adjustments:
        rows.append(
            "<tr>"
            f"<td>{escape(str(row.date))}</td>"
            f"<td>{escape(row.location_name)} ({escape(row.location_id)})</td>"
            f"<td>{escape(_format_money(row.gross_amt))}</td>"
            f"<td>{escape(_format_money(row.fees))}</td>"
            f"<td>{escape(_format_money(row.net_amt))}</td>"
            f"<td>{escape(str(row.source_code or ''))}</td>"
            "</tr>"
        )

    return "\n".join(["<h4>Mobile adjustments</h4>", "<table>", *rows, "</table>"])


def _build_html_valero_pay_plus_table(report: ParsedReport) -> str:
    rows_data = getattr(report, "valero_pay_plus_adjustments", []) or []

    if not rows_data:
        return ""

    rows = [
        "<tr><th>Date</th><th>Location</th><th>Amount</th><th>Source</th></tr>"
    ]

    for row in rows_data:
        rows.append(
            "<tr>"
            f"<td>{escape(str(row.date))}</td>"
            f"<td>{escape(row.location_name)} ({escape(row.location_id)})</td>"
            f"<td>{escape(_format_money(row.amount))}</td>"
            f"<td>{escape(str(row.source_code or ''))}</td>"
            "</tr>"
        )

    return "\n".join(["<h4>Valero Pay+</h4>", "<table>", *rows, "</table>"])


def _build_html_valero_monthly_charges_table(report: ParsedReport) -> str:
    rows_data = getattr(report, "valero_monthly_charges", []) or []

    if not rows_data:
        return ""

    rows = [
        "<tr><th>Date</th><th>Location</th><th>Amount</th><th>Description</th></tr>"
    ]

    for row in rows_data:
        rows.append(
            "<tr>"
            f"<td>{escape(str(row.date))}</td>"
            f"<td>{escape(row.location_name)} ({escape(row.location_id)})</td>"
            f"<td>{escape(_format_money(row.amount))}</td>"
            f"<td>{escape(row.description)}</td>"
            "</tr>"
        )

    return "\n".join(["<h4>Valero monthly charges</h4>", "<table>", *rows, "</table>"])


def _build_html_unclassified_adjustments_table(report: ParsedReport) -> str:
    rows_data = getattr(report, "unclassified_adjustments", []) or []

    if not rows_data:
        return ""

    rows = [
        "<tr><th>Report date</th><th>Location</th><th>Amount</th><th>Description</th><th>Raw line</th></tr>"
    ]

    for row in rows_data:
        amount = _format_money(row.amount) if row.amount is not None else "-"
        rows.append(
            "<tr>"
            f"<td>{escape(str(row.report_date))}</td>"
            f"<td>{escape(str(row.location_name))} ({escape(str(row.location_id))})</td>"
            f"<td>{escape(amount)}</td>"
            f"<td>{escape(row.description)}</td>"
            f"<td>{escape(row.raw_line)}</td>"
            "</tr>"
        )

    return "\n".join(["<h4>Unclassified adjustments</h4>", "<table>", *rows, "</table>"])


def _html_row(label: str, value: Any) -> str:
    return (
        "<tr>"
        f"<th>{escape(str(label))}</th>"
        f"<td>{escape(str(value))}</td>"
        "</tr>"
    )


def _format_money(value: Decimal | None) -> str:
    if value is None:
        return "-"

    return f"${value:,.2f}"


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "-"

    return value.isoformat(sep=" ", timespec="seconds")


def _format_value(value: object) -> str:
    if isinstance(value, Decimal):
        return _format_money(value)

    return str(value)


def _format_optional_detail(label: str, value: object | None) -> str:
    if value is None or value == "":
        return ""

    return f" | {label}: {value}"


def write_daily_email_preview(
    *,
    email: DailyEmailContent,
    summary: DailyRunSummary,
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    base_name = f"{summary.business_date.isoformat()}_daily_summary"

    text_path = output_dir / f"{base_name}.txt"
    html_path = output_dir / f"{base_name}.html"

    text_path.write_text(
        _format_preview_text(email),
        encoding="utf-8",
    )

    html_path.write_text(
        email.html,
        encoding="utf-8",
    )

    return text_path, html_path


def _format_preview_text(email: DailyEmailContent) -> str:
    return (
        f"Subject: {email.subject}\n"
        "\n"
        f"{email.plain_text}"
    )


def handle_daily_notification(
    summary: DailyRunSummary,
    config: NotificationConfig | None = None,
) -> NotificationResult:
    config = config or load_notification_config()

    if config.is_off:
        return NotificationResult(
            enabled=False,
            mode=config.mode,
            provider=config.provider,
            sent=False,
        )

    email = build_daily_email(summary)

    preview_text_path = None
    preview_html_path = None

    if config.should_write_preview:
        preview_text_path, preview_html_path = write_daily_email_preview(
            email=email,
            summary=summary,
            output_dir=config.output_dir,
        )

    if config.should_send:
        if config.provider == "graph":
            sender = GraphEmailSender(
                GraphEmailConfig(
                    tenant_id=config.graph_tenant_id,
                    client_id=config.graph_client_id,
                    client_secret=config.graph_client_secret,
                    sender_email=config.graph_sender_email,
                )
            )
        else:
            return NotificationResult(
                enabled=True,
                mode=config.mode,
                provider=config.provider,
                sent=False,
                preview_text_path=preview_text_path,
                preview_html_path=preview_html_path,
                error_message="SMTP sender is not implemented yet.",
            )

        send_result = sender.send(
            email=email,
            recipients=build_email_recipients(config),
        )

        return NotificationResult(
            enabled=True,
            mode=config.mode,
            provider=config.provider,
            sent=send_result.sent,
            preview_text_path=preview_text_path,
            preview_html_path=preview_html_path,
            error_message=send_result.error_message,
        )