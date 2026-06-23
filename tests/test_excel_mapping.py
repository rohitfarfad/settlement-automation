from datetime import date

from config.excel_mapping import (
    get_month_sheet_candidates,
    normalize_excel_text,
    resolve_month_sheet_name,
)


def test_normalize_excel_text():
    assert normalize_excel_text(" Gross AMT ") == "GROSS AMT"
    assert normalize_excel_text("CC-Fee") == "CC FEE"
    assert normalize_excel_text("MOBILE  PAY") == "MOBILE PAY"


def test_get_month_sheet_candidates_supports_short_and_long_names():
    assert get_month_sheet_candidates(date(2026, 6, 15)) == (
        "JUN 2026",
        "JUNE 2026",
    )


def test_resolve_month_sheet_name_accepts_full_month_name():
    sheets = [
        "JAN 2026",
        "FEB 2026",
        "MAR 2026",
        "APRIL 2026",
        "MAY 2026",
        "JUNE 2026",
    ]

    assert resolve_month_sheet_name(sheets, date(2026, 6, 15)) == "JUNE 2026"


def test_resolve_month_sheet_name_accepts_abbreviated_month_name():
    sheets = [
        "JAN 2026",
        "FEB 2026",
        "MAR 2026",
        "APR 2026",
        "MAY 2026",
        "JUN 2026",
    ]

    assert resolve_month_sheet_name(sheets, date(2026, 6, 15)) == "JUN 2026"


def test_resolve_month_sheet_name_returns_none_if_missing():
    sheets = ["JAN 2026", "FEB 2026"]

    assert resolve_month_sheet_name(sheets, date(2026, 6, 15)) is None