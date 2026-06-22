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