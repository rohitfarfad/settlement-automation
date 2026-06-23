from datetime import date

from settlement_automation.connectors.sunoco_date import (
    get_sunoco_portal_request_date,
    get_sunoco_settlement_date_for_business_date,
)


def test_sunoco_portal_request_date_is_business_date_plus_one():
    business_date = date(2026, 6, 16)

    assert get_sunoco_portal_request_date(business_date) == date(2026, 6, 17)


def test_backward_compatible_alias_returns_same_portal_request_date():
    business_date = date(2026, 6, 16)

    assert get_sunoco_settlement_date_for_business_date(business_date) == date(
        2026, 6, 17
    )