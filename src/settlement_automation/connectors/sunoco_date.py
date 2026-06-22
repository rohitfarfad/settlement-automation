from datetime import date, timedelta


def get_sunoco_portal_request_date(business_date: date) -> date:
    """
    Sunoco portal reports are requested by settlement date.

    The parser already understands that settlementDate in the JSON maps to
    the prior business date. This helper is only for choosing the portal date
    to request.
    """
    return business_date + timedelta(days=1)