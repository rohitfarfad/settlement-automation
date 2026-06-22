from datetime import date

from settlement_automation.connectors.dtn_date import format_dtn_dropdown_date


def test_format_dtn_dropdown_date_wednesday():
    assert format_dtn_dropdown_date(date(2026, 6, 17)) == "June 17,2026 (Wed)"


def test_format_dtn_dropdown_date_friday():
    assert format_dtn_dropdown_date(date(2026, 6, 19)) == "June 19,2026 (Fri)"


def test_format_dtn_dropdown_date_single_digit_day():
    assert format_dtn_dropdown_date(date(2026, 6, 5)) == "June 5,2026 (Fri)"