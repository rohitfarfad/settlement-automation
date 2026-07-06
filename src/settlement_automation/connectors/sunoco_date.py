from datetime import date


def get_sunoco_portal_request_date(requested_report_date: date) -> date:
    """
    Return the Sunoco report date to request from the portal/API.

    Important:
    The parser already converts Sunoco settlementDate/reportDate into the
    business date by subtracting one day.

    Therefore, the fetcher should request exactly the date supplied by the
    caller. The caller's date is treated as the Sunoco report/settlement date,
    not the final Excel business date.
    """
    return requested_report_date


def get_sunoco_settlement_date_for_business_date(requested_report_date: date) -> date:
    """
    Backward-compatible alias.

    Older code treated the input as business_date and added one day.
    New behavior treats the input as requested report date directly.
    """
    return get_sunoco_portal_request_date(requested_report_date)