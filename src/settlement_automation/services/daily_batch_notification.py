from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from html import escape
from pathlib import Path

from settlement_automation.services.daily_pipeline import DailyPipelineResult
from settlement_automation.services.email_models import DailyEmailContent
from settlement_automation.services.email_senders import (
    GraphEmailConfig,
    GraphEmailSender,
)
from settlement_automation.services.notifications import (
    NotificationConfig,
    NotificationResult,
    build_daily_email,
    build_email_recipients,
    load_notification_config,
)
from settlement_automation.services.notification_pdfs import (
    build_supplier_pdf_attachments,
)


@dataclass(frozen=True)
class DailyBatchRun:
    name: str
    report_date: date
    result: DailyPipelineResult


def handle_daily_batch_notification(
    *,
    task_date: date,
    runs: list[DailyBatchRun],
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

    email = build_daily_batch_email(
        task_date=task_date,
        runs=runs,
    )

    pdf_attachments = []
    pdf_attachment_paths = []

    if config.should_write_preview or config.should_send:
        for run in runs:
            run_attachments, run_paths = build_supplier_pdf_attachments(
                summary=run.result.summary,
                output_dir=config.output_dir,
            )
            pdf_attachments.extend(run_attachments)
            pdf_attachment_paths.extend(run_paths)

    preview_text_path = None
    preview_html_path = None

    if config.should_write_preview:
        preview_text_path, preview_html_path = write_daily_batch_email_preview(
            email=email,
            task_date=task_date,
            output_dir=config.output_dir,
        )

    if config.should_send:
        if config.provider != "graph":
            return NotificationResult(
                enabled=True,
                mode=config.mode,
                provider=config.provider,
                sent=False,
                preview_text_path=preview_text_path,
                preview_html_path=preview_html_path,
                error_message="SMTP sender is not implemented yet.",
            )

        sender = GraphEmailSender(
            GraphEmailConfig(
                tenant_id=config.graph_tenant_id,
                client_id=config.graph_client_id,
                client_secret=config.graph_client_secret,
                sender_email=config.graph_sender_email,
            )
        )

        send_result = sender.send(
            email=email,
            recipients=build_email_recipients(config),
            attachments=pdf_attachments,
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

    return NotificationResult(
        enabled=True,
        mode=config.mode,
        provider=config.provider,
        sent=False,
        preview_text_path=preview_text_path,
        preview_html_path=preview_html_path,
    )


def build_daily_batch_email(
    *,
    task_date: date,
    runs: list[DailyBatchRun],
) -> DailyEmailContent:
    status = _batch_status(runs)

    subject = (
        f"[{status}] Credit Cards Daily Settlement Batch "
        f"- Run Date {task_date.isoformat()}"
    )

    plain_text = _build_batch_plain_text(
        task_date=task_date,
        status=status,
        runs=runs,
    )

    html = _build_batch_html(
        task_date=task_date,
        status=status,
        runs=runs,
    )

    return DailyEmailContent(
        subject=subject,
        plain_text=plain_text,
        html=html,
    )


def write_daily_batch_email_preview(
    *,
    email: DailyEmailContent,
    task_date: date,
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    base_name = f"{task_date.isoformat()}_daily_batch_summary"
    text_path = output_dir / f"{base_name}.txt"
    html_path = output_dir / f"{base_name}.html"

    text_path.write_text(
        f"Subject: {email.subject}\n\n{email.plain_text}",
        encoding="utf-8",
    )
    html_path.write_text(email.html, encoding="utf-8")

    return text_path, html_path


def _batch_status(runs: list[DailyBatchRun]) -> str:
    if any(run.result.summary.has_errors for run in runs):
        return "ERROR"

    if any(run.result.summary.has_warnings for run in runs):
        return "WARNING"

    return "OK"


def _build_batch_plain_text(
    *,
    task_date: date,
    status: str,
    runs: list[DailyBatchRun],
) -> str:
    lines: list[str] = []

    lines.append("Prestige Settlement Daily Batch Report")
    lines.append("=" * 60)
    lines.append(f"Run date: {task_date.isoformat()}")
    lines.append(f"Status: {status}")
    lines.append("")

    lines.append("Batch summary")
    lines.append("-" * 60)

    for run in runs:
        summary = run.result.summary

        lines.append(
            f"- {run.name}: report_date={run.report_date.isoformat()}, "
            f"status={_run_status_label(run)}, "
            f"suppliers={', '.join(summary.supplier_names) or '-'}, "
            f"daily_totals={summary.daily_total_count}, "
            f"excel_written={summary.excel_written_count}, "
            f"errors={summary.error_count}, "
            f"warnings={summary.warning_count}"
        )

    lines.append("")

    for run in runs:
        lines.append("")
        lines.append("=" * 60)
        lines.append(
            f"{run.name} | Report date {run.report_date.isoformat()}"
        )
        lines.append("=" * 60)

        email = build_daily_email(run.result.summary)
        lines.append(email.plain_text.strip())

    return "\n".join(lines).rstrip() + "\n"


def _build_batch_html(
    *,
    task_date: date,
    status: str,
    runs: list[DailyBatchRun],
) -> str:
    summary_rows = []

    for run in runs:
        summary = run.result.summary

        summary_rows.append(
            "<tr>"
            f"<td>{escape(run.name)}</td>"
            f"<td>{escape(run.report_date.isoformat())}</td>"
            f"<td>{escape(_run_status_label(run))}</td>"
            f"<td>{escape(', '.join(summary.supplier_names) or '-')}</td>"
            f"<td>{summary.daily_total_count}</td>"
            f"<td>{summary.excel_written_count}</td>"
            f"<td>{summary.warning_count}</td>"
            f"<td>{summary.error_count}</td>"
            "</tr>"
        )

    run_sections = []

    for run in runs:
        email = build_daily_email(run.result.summary)

        run_sections.append(
            "<section class='card'>"
            f"<h2>{escape(run.name)}</h2>"
            f"<p><strong>Report date:</strong> "
            f"{escape(run.report_date.isoformat())}</p>"
            f"{email.html}"
            "</section>"
        )

    return "\n".join(
        [
            "<!doctype html>",
            "<html>",
            "<head>",
            "<meta charset='utf-8'>",
            "<style>",
            "body { font-family: Arial, sans-serif; color: #222; }",
            ".page { max-width: 1100px; margin: 0 auto; padding: 24px; }",
            ".notice { padding: 12px 16px; border-radius: 6px; margin: 12px 0 20px; }",
            ".notice-ok { background: #e9f7ef; border: 1px solid #9bd4b4; }",
            ".notice-warning { background: #fff7e6; border: 1px solid #f0c36d; }",
            ".notice-error { background: #fdecea; border: 1px solid #e09a9a; }",
            ".card { border: 1px solid #ddd; border-radius: 8px; padding: 16px; margin: 20px 0; }",
            "table { border-collapse: collapse; width: 100%; margin: 12px 0 18px; }",
            "th, td { border: 1px solid #ccc; padding: 8px 10px; text-align: left; vertical-align: top; }",
            "th { background: #f5f5f5; }",
            ".amount { text-align: right; white-space: nowrap; }",
            "</style>",
            "</head>",
            "<body>",
            "<div class='page'>",
            "<h1>Prestige Settlement Daily Batch Report</h1>",
            f"<div class='{_status_class(status)}'>",
            f"<strong>Status:</strong> {escape(status)}<br>",
            f"<strong>Run date:</strong> {escape(task_date.isoformat())}",
            "</div>",
            "<h2>Batch summary</h2>",
            "<table>",
            "<thead>",
            "<tr>",
            "<th>Run</th>",
            "<th>Report date</th>",
            "<th>Status</th>",
            "<th>Suppliers</th>",
            "<th>Daily totals</th>",
            "<th>Excel written</th>",
            "<th>Warnings</th>",
            "<th>Errors</th>",
            "</tr>",
            "</thead>",
            "<tbody>",
            *summary_rows,
            "</tbody>",
            "</table>",
            *run_sections,
            "</div>",
            "</body>",
            "</html>",
        ]
    )


def _run_status_label(run: DailyBatchRun) -> str:
    summary = run.result.summary

    if summary.has_errors:
        return "ERROR"

    if summary.has_warnings:
        return "WARNING"

    return "OK"


def _status_class(status: str) -> str:
    if status == "ERROR":
        return "notice notice-error"

    if status == "WARNING":
        return "notice notice-warning"

    return "notice notice-ok"