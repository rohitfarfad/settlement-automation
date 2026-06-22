from datetime import date

from settlement_automation.connectors.sunoco_date import (
    get_business_date_from_sunoco_settlement_date,
    get_sunoco_settlement_date_for_business_date,
)


def test_sunoco_settlement_date_is_business_date_plus_one():
    business_date = date(2026, 6, 16)

    assert get_sunoco_settlement_date_for_business_date(business_date) == date(
        2026, 6, 17
    )


def test_sunoco_business_date_is_settlement_date_minus_one():
    settlement_date = date(2026, 6, 17)

    assert get_business_date_from_sunoco_settlement_date(settlement_date) == date(
        2026, 6, 16
    )