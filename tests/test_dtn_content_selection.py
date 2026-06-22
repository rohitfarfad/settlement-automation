from config.dtn_reports import get_dtn_report_target
from settlement_automation.connectors.dtn_content_selection import (
    report_matches_required_content,
)


def test_citgo_accepts_daily_transaction_summary():
    target = get_dtn_report_target("citgo")

    text = """
    CITGO PETROLEUM
    K4SY              CITGO DAILY RECEIVED TRANSACTION SUMMARY   06/17/26 18:17:02
    """

    assert report_matches_required_content(text, target) is True


def test_citgo_rejects_prepaid_card_activations():
    target = get_dtn_report_target("citgo")

    text = """
    CITGO PETROLEUM
    L3EB                         PREPAID CARD ACTIVATIONS           06/17/26 18:17
    """

    assert report_matches_required_content(text, target) is False


def test_citgo_rejects_missing_required_marker():
    target = get_dtn_report_target("citgo")

    text = """
    CITGO PETROLEUM
    CREDIT CARD MEMO
    """

    assert report_matches_required_content(text, target) is False


def test_valero_accepts_when_no_required_marker_configured():
    target = get_dtn_report_target("valero")

    text = "VALERO R & M CREDIT CARD MEMO"

    assert report_matches_required_content(text, target) is True