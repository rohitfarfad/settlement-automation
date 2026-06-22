from datetime import datetime, date


def parse_mmdd(mmdd: str, year: int) -> date:
    return datetime.strptime(f"{year}{mmdd}", "%Y%m%d").date()


def parse_mmddyy(value: str) -> date:
    value = value.strip().replace("-", "/")
    return datetime.strptime(value, "%m/%d/%y").date()