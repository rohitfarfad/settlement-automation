from datetime import date, datetime
from decimal import Decimal

from settlement_automation.models import DailySettlementTotal, ParsedReport
from settlement_automation.services.daily_run_summary import (
    RunError,
    build_daily_run_summary,
)
from settlement_automation.services.notifications import build_daily_email


def test_build_daily_email_success_subject():
    report = ParsedReport(
        supplier="VALERO",
        report_date=date(2026, 7, 1),
        daily_totals=[
            DailySettlementTotal(
                supplier="VALERO",
                location_id="19505",
                location_name="TEST LOCATION",
                date=date(2026, 7, 1),
                gross_amt=Decimal("100.00"),
                fees=Decimal("2.00"),
                net_amt=Decimal("98.00"),
            )
        ],
        mobile_adjustments=[],
    )

    summary = build_daily_run_summary(
        business_date=date(2026, 7, 1),
        run_date=date(2026, 7, 1),
        started_at=datetime(2026, 7, 1, 8, 0, 0),
        finished_at=datetime(2026, 7, 1, 8, 5, 0),
        parsed_reports=[report],
    )

    email = build_daily_email(summary)

    assert email.subject == (
        "[OK] Prestige Settlement Daily Report "
        "- Business Date 2026-07-01"
    )
    assert "Daily totals: 1" in email.plain_text
    assert "TEST LOCATION" in email.plain_text
    assert "$100.00" in email.plain_text
    assert "<h1>Prestige Settlement Daily Report</h1>" in email.html


def test_build_daily_email_warning_subject_for_anomaly():
    report = ParsedReport(
        supplier="CITGO",
        report_date=date(2026, 7, 11),
        daily_totals=[
            DailySettlementTotal(
                supplier="CITGO",
                location_id="15861002",
                location_name="HAVERSTRAW",
                date=date(2026, 6, 30),
                gross_amt=Decimal("100.00"),
                fees=Decimal("2.00"),
                net_amt=Decimal("98.00"),
            )
        ],
        mobile_adjustments=[],
    )

    summary = build_daily_run_summary(
        business_date=date(2026, 7, 11),
        run_date=date(2026, 7, 11),
        started_at=datetime(2026, 7, 11, 8, 0, 0),
        parsed_reports=[report],
    )

    email = build_daily_email(summary)

    assert email.subject.startswith("[WARNING]")
    assert "PREVIOUS_MONTH_AFTER_10TH" in email.plain_text


def test_build_daily_email_error_subject():
    summary = build_daily_run_summary(
        business_date=date(2026, 7, 1),
        run_date=date(2026, 7, 1),
        started_at=datetime(2026, 7, 1, 8, 0, 0),
        errors=[
            RunError(
                stage="fetch",
                supplier="VALERO",
                message="Report not found on portal.",
            )
        ],
    )

    email = build_daily_email(summary)

    assert email.subject.startswith("[ERROR]")
    assert "Report not found on portal." in email.plain_text
    assert "[fetch]" in email.plain_text


def test_build_daily_email_uses_correct_amount_field_names():
    report = ParsedReport(
        supplier="VALERO",
        report_date=date(2026, 7, 1),
        daily_totals=[
            DailySettlementTotal(
                supplier="VALERO",
                location_id="19505",
                location_name="TEST LOCATION",
                date=date(2026, 7, 1),
                gross_amt=Decimal("123.45"),
                fees=Decimal("3.45"),
                net_amt=Decimal("120.00"),
            )
        ],
        mobile_adjustments=[],
    )

    summary = build_daily_run_summary(
        business_date=date(2026, 7, 1),
        run_date=date(2026, 7, 1),
        started_at=datetime(2026, 7, 1, 8, 0, 0),
        parsed_reports=[report],
    )

    email = build_daily_email(summary)

    assert "Gross $123.45" in email.plain_text
    assert "Fees $3.45" in email.plain_text
    assert "Net $120.00" in email.plain_text


from pathlib import Path
from datetime import date, datetime
from decimal import Decimal

from settlement_automation.models import DailySettlementTotal, ParsedReport
from settlement_automation.services.daily_run_summary import build_daily_run_summary
from settlement_automation.services.notifications import (
    NotificationConfig,
    handle_daily_notification,
)


def test_handle_daily_notification_dry_run_writes_preview(tmp_path):
    report = ParsedReport(
        supplier="VALERO",
        report_date=date(2026, 7, 1),
        daily_totals=[
            DailySettlementTotal(
                supplier="VALERO",
                location_id="19505",
                location_name="TEST LOCATION",
                date=date(2026, 7, 1),
                gross_amt=Decimal("100.00"),
                fees=Decimal("2.00"),
                net_amt=Decimal("98.00"),
            )
        ],
        mobile_adjustments=[],
    )

    summary = build_daily_run_summary(
        business_date=date(2026, 7, 1),
        run_date=date(2026, 7, 1),
        started_at=datetime(2026, 7, 1, 8, 0, 0),
        parsed_reports=[report],
    )

    config = NotificationConfig(
        enabled=True,
        mode="dry_run",
        provider="graph",
        output_dir=tmp_path,
    )

    result = handle_daily_notification(summary, config)

    assert result.enabled is True
    assert result.mode == "dry_run"
    assert result.provider == "graph"
    assert result.sent is False
    assert result.preview_text_path is not None
    assert result.preview_html_path is not None
    assert result.preview_text_path.exists()
    assert result.preview_html_path.exists()

    text = result.preview_text_path.read_text(encoding="utf-8")
    html = result.preview_html_path.read_text(encoding="utf-8")

    assert "Subject: [OK] Prestige Settlement Daily Report" in text
    assert "TEST LOCATION" in text
    assert "<h1>Prestige Settlement Daily Report</h1>" in html

def test_handle_daily_notification_disabled_does_not_write_files(tmp_path):
    summary = build_daily_run_summary(
        business_date=date(2026, 7, 1),
        run_date=date(2026, 7, 1),
        started_at=datetime(2026, 7, 1, 8, 0, 0),
    )

    config = NotificationConfig(
        enabled=False,
        mode="off",
        provider="graph",
        output_dir=tmp_path,
    )

    result = handle_daily_notification(summary, config)

    assert result.enabled is False
    assert result.sent is False
    assert result.preview_text_path is None
    assert result.preview_html_path is None
    assert list(tmp_path.iterdir()) == []

def test_handle_daily_notification_test_mode_generates_preview_but_does_not_send_yet(tmp_path):
    summary = build_daily_run_summary(
        business_date=date(2026, 7, 1),
        run_date=date(2026, 7, 1),
        started_at=datetime(2026, 7, 1, 8, 0, 0),
    )

    config = NotificationConfig(
        enabled=True,
        mode="test",
        provider="graph",
        output_dir=tmp_path,
    )

    result = handle_daily_notification(summary, config)

    assert result.enabled is True
    assert result.mode == "test"
    assert result.sent is False
    assert result.preview_text_path is not None
    assert result.preview_html_path is not None
    assert result.error_message is not None
    assert "Missing Microsoft Graph config values" in result.error_message
    assert "GRAPH_TENANT_ID" in result.error_message
    assert "GRAPH_CLIENT_ID" in result.error_message
    assert "GRAPH_CLIENT_SECRET" in result.error_message
    assert "GRAPH_SENDER_EMAIL" in result.error_message
from settlement_automation.services.notifications import (
    NotificationConfig,
    handle_daily_notification,
)
from settlement_automation.services.daily_run_summary import (
    build_daily_run_summary,
)
from datetime import date, datetime


def test_handle_daily_notification_test_mode_graph_missing_config_returns_error(tmp_path):
    summary = build_daily_run_summary(
        business_date=date(2026, 7, 1),
        run_date=date(2026, 7, 1),
        started_at=datetime(2026, 7, 1, 8, 0, 0),
    )

    config = NotificationConfig(
        enabled=True,
        mode="test",
        provider="graph",
        output_dir=tmp_path,
        email_test_to="test@example.com",
    )

    result = handle_daily_notification(summary, config)

    assert result.enabled is True
    assert result.mode == "test"
    assert result.provider == "graph"
    assert result.sent is False
    assert result.preview_text_path is not None
    assert result.preview_html_path is not None
    assert result.error_message is not None
    assert "GRAPH_TENANT_ID" in result.error_message