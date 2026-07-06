from decimal import Decimal
from pathlib import Path

from settlement_automation.parsers.valero_parser import parse_valero_report


def write_report(tmp_path, body: str) -> str:
    path = tmp_path / "valero_unknown_adjustment.txt"
    path.write_text(body, encoding="utf-8")
    return str(path)


def test_valero_unknown_adjustment_is_captured(tmp_path):
    report_text = """
MSR/DTN: 06/18/26

DEALER 19505 TEST LOCATION
SUB 0617 1 100.00+ 0.00+ 2.00+ 98.00+

19505  SOME OTHER ADJUSTMENT DESCRIPTION                            42.15-
"""

    report = parse_valero_report(write_report(tmp_path, report_text))

    assert len(report.unclassified_adjustments) == 1

    adjustment = report.unclassified_adjustments[0]
    assert adjustment.supplier == "VALERO"
    assert adjustment.location_id == "19505"
    assert adjustment.location_name == "TEST LOCATION"
    assert adjustment.amount == Decimal("-42.15")
    assert adjustment.description == "SOME OTHER ADJUSTMENT DESCRIPTION"
    assert "SOME OTHER ADJUSTMENT DESCRIPTION" in adjustment.raw_line



def test_valero_monthly_charge_is_not_unclassified(tmp_path):
    report_text = """
MSR/DTN: 06/18/26

DEALER 19505 TEST LOCATION
SUB 0617 1 100.00+ 0.00+ 2.00+ 98.00+

19505  MONTHLY TNSLinkMNSP48 1X24 BILLING                          113.79-
"""

    report = parse_valero_report(write_report(tmp_path, report_text))

    assert len(report.valero_monthly_charges) == 1
    assert len(report.unclassified_adjustments) == 0


def test_valero_payplus_is_not_unclassified(tmp_path):
    report_text = """
MSR/DTN: 06/18/26

DEALER 19505 TEST LOCATION
SUB 0617 1 100.00+ 0.00+ 2.00+ 98.00+

19505 CRND VISA VP+ Fuel Offer 06-17 12.34-
"""

    report = parse_valero_report(write_report(tmp_path, report_text))

    assert len(report.valero_pay_plus_adjustments) == 1
    assert len(report.unclassified_adjustments) == 0


def test_valero_unclassified_adjustments_only_from_adjustments_section(tmp_path):
    report_text = """
VALERO
MSR/DTN:  07/01/26

DEALER CREDITS
DATE   IO/CARD/TRX     COUNT        GROSS       DISC        FEE           NET

DEALER 11347 Route 44 Valero

  0629 CRND VPVS PUR       2        85.76+      1.59-      0.22-        83.95+
       SUB  CRIND          2        85.76+      1.59-      0.22-        83.95+

       SUB  0629           2        85.76+      1.59-      0.22-        83.95+

  0630 POS  VISA PUR       1       100.00+      1.00-      2.00-        97.00+
       SUB  POS            1       100.00+      1.00-      2.00-        97.00+

       SUB  0630           1       100.00+      1.00-      2.00-        97.00+

TOTAL  11347               3       185.76+      2.59-      2.22-       180.95+

  ADJUSTMENTS
    DEALER DESCRIPTION                                          ADJUSTMENT AMT
    11347  CRND VALP VP+ Fuel Offer 06-30                                1.99+
    TOTAL  ADJUSTMENTS                                                   1.99+
"""

    path = tmp_path / "valero.txt"
    path.write_text(report_text, encoding="utf-8")

    report = parse_valero_report(str(path))

    assert len(report.daily_totals) == 1
    assert len(report.mobile_adjustments) == 1
    assert len(report.valero_pay_plus_adjustments) == 1
    assert len(report.unclassified_adjustments) == 0