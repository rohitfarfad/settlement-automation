from datetime import date, timedelta


def get_sunoco_portal_request_date(business_date: date) -> date:
    """
    Sunoco portal reports are searched by settlement date.

    Parser already handles:
        JSON settlementDate -> business_date = settlementDate - 1 day

    This helper is only for choosing the date to search in the portal.
    """
    return business_date + timedelta(days=1)


def get_sunoco_settlement_date_for_business_date(business_date: date) -> date:
    """
    Backward-compatible alias.

    Older Sunoco connector skeleton imported this name.
    Keep this so old code does not break.
    """
    return get_sunoco_portal_request_date(business_date)