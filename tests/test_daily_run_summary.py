from datetime import date, datetime
from decimal import Decimal

from settlement_automation.models import DailySettlementTotal, ParsedReport
from settlement_automation.services.daily_run_summary import (
    build_daily_run_summary,
)
from datetime import date, datetime
from decimal import Decimal

from settlement_automation.models import (
    ParsedReport,
    UnclassifiedAdjustment,
)
from settlement_automation.services.daily_run_summary import (
    RunError,
    build_daily_run_summary,
)


def test_build_daily_run_summary_empty():
    summary = build_daily_run_summary(
        business_date=date(2026, 7, 1),
        run_date=date(2026, 7, 1),
        started_at=datetime(2026, 7, 1, 8, 0, 0),
    )

    assert summary.business_date == date(2026, 7, 1)
    assert summary.run_date == date(2026, 7, 1)
    assert summary.daily_total_count == 0
    assert summary.warning_count == 0
    assert summary.error_count == 0
    assert not summary.has_errors
    assert not summary.has_warnings


def test_daily_run_summary_counts_daily_totals():
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

    assert summary.supplier_names == ["VALERO"]
    assert summary.daily_total_count == 1


def test_daily_run_summary_includes_anomalies():
    report = ParsedReport(
        supplier="VALERO",
        report_date=date(2026, 7, 1),
        daily_totals=[],
        mobile_adjustments=[],
        unclassified_adjustments=[
            UnclassifiedAdjustment(
                supplier="VALERO",
                location_id="19505",
                location_name="TEST LOCATION",
                report_date=date(2026, 7, 1),
                amount=Decimal("-42.15"),
                description="SOME OTHER ADJUSTMENT",
                raw_line="19505  SOME OTHER ADJUSTMENT  42.15-",
            )
        ],
    )

    summary = build_daily_run_summary(
        business_date=date(2026, 7, 1),
        run_date=date(2026, 7, 1),
        started_at=datetime(2026, 7, 1, 8, 0, 0),
        parsed_reports=[report],
    )

    assert len(summary.anomalies) == 1
    assert summary.anomalies[0].code == "UNCLASSIFIED_ADJUSTMENT"
    assert summary.warning_count == 1
    assert summary.has_warnings


def test_daily_run_summary_counts_errors():
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

    assert summary.error_count == 1
    assert summary.has_errors