from dataclasses import dataclass, field
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
class ValeroPayPlusAdjustment:
    supplier: str
    location_id: str
    location_name: str
    date: date
    amount: Decimal
    source_code: str | None = None


@dataclass
class ValeroMonthlyCharge:
    supplier: str
    location_id: str
    location_name: str
    date: date
    amount: Decimal
    description: str

@dataclass(frozen=True)
class UnclassifiedAdjustment:
    supplier: str
    location_id: str | None
    location_name: str | None
    report_date: date
    amount: Decimal | None
    description: str
    raw_line: str


@dataclass
class ParsedReport:
    supplier: str
    report_date: date
    daily_totals: list[DailySettlementTotal]
    mobile_adjustments: list[MobileAdjustment]
    valero_pay_plus_adjustments: list[ValeroPayPlusAdjustment] = field(default_factory=list)
    valero_monthly_charges: list[ValeroMonthlyCharge] = field(default_factory=list)
    unclassified_adjustments: list[UnclassifiedAdjustment] = field(default_factory=list)