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