from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass
class DailySettlementTotal:
    supplier: str
    location_id: str
    location_name: str
    date: date
    gross_amt: Decimal
    fees: Decimal
    net_amt: Decimal


@dataclass
class MobileAdjustment:
    supplier: str
    location_id: str
    location_name: str
    date: date
    gross_amt: Decimal
    fees: Decimal
    net_amt: Decimal
    source_code: str | None = None


@dataclass
class ParsedReport:
    supplier: str
    report_date: date
    daily_totals: list[DailySettlementTotal]
    mobile_adjustments: list[MobileAdjustment]