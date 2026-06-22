from decimal import Decimal


def parse_money(value: str) -> Decimal:
    value = value.strip().replace(",", "")

    if value.endswith("-"):
        return -Decimal(value[:-1])

    if value.endswith("+"):
        return Decimal(value[:-1])

    return Decimal(value)