from datetime import date

from settlement_automation.connectors.dtn_date import (
    get_dtn_date_label_candidates,
    normalize_dtn_date_label,
)


def test_dtn_date_label_candidates_include_zero_padded_day():
    labels = get_dtn_date_label_candidates(date(2026, 6, 5))

    assert "June 05,2026 (Fri)" in labels
    assert "June 5,2026 (Fri)" in labels


def test_dtn_date_label_candidates_for_double_digit_day():
    labels = get_dtn_date_label_candidates(date(2026, 6, 17))

    assert "June 17,2026 (Wed)" in labels


def test_normalize_dtn_date_label_handles_zero_padded_day():
    assert normalize_dtn_date_label("June 05,2026 (Fri)") == normalize_dtn_date_label(
        "June 5,2026 (Fri)"
    )


def test_normalize_dtn_date_label_keeps_double_digit_day_consistent():
    assert normalize_dtn_date_label("June 17,2026 (Wed)") == "june 17,2026 (wed)"