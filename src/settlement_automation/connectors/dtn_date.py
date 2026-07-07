from __future__ import annotations

import re
from datetime import date


def format_dtn_dropdown_date(value: date) -> str:
    """
    Format a date exactly like the DTN DataConnect dropdown.

    Example:
        date(2026, 6, 17) -> "June 17,2026 (Wed)"
    """
    month_name = value.strftime("%B")
    day = value.day
    year = value.year
    weekday = value.strftime("%a")

    return f"{month_name} {day},{year} ({weekday})"


def get_dtn_date_label_candidates(business_date: date) -> list[str]:
    """
    DTN date labels have been observed as:

        June 05,2026 (Fri)

    But earlier code may generate:

        June 5,2026 (Fri)

    Return both formats.
    """
    month = business_date.strftime("%B")
    day_zero = f"{business_date.day:02d}"
    day_plain = str(business_date.day)
    year = f"{business_date.year:04d}"
    weekday = business_date.strftime("%a")

    return [
        f"{month} {day_zero},{year} ({weekday})",
        f"{month} {day_plain},{year} ({weekday})",
    ]


def get_dtn_date_value_candidates(business_date: date) -> list[str]:
    """
    Possible option values if DTN stores machine-readable values.

    Important:
    Do not use Unix-only strftime directives like %-m or %-d.
    They fail on Windows with: ValueError: Invalid format string.
    """
    year = f"{business_date.year:04d}"
    month_zero = f"{business_date.month:02d}"
    day_zero = f"{business_date.day:02d}"
    month_plain = str(business_date.month)
    day_plain = str(business_date.day)

    return [
        f"{year}{month_zero}{day_zero}",
        f"{month_zero}/{day_zero}/{year}",
        f"{month_plain}/{day_plain}/{year}",
        business_date.isoformat(),
    ]


def normalize_dtn_date_label(value: str) -> str:
    """
    Normalize labels so these compare equal:

        June 05,2026 (Fri)
        June 5,2026 (Fri)
    """
    value = " ".join((value or "").split())

    match = re.match(
        r"^([A-Za-z]+)\s+0?(\d{1,2}),(\d{4})\s+\(([A-Za-z]{3})\)$",
        value,
    )

    if not match:
        return value.lower()

    month, day, year, weekday = match.groups()

    return f"{month.lower()} {int(day)},{year} ({weekday.lower()})"