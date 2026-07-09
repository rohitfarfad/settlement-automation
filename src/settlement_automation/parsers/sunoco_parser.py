import json
from datetime import datetime, timedelta, date
from decimal import Decimal
from pathlib import Path

from settlement_automation.models import (
    DailySettlementTotal,
    ParsedReport,
    SunocoCreditCardDiscount,
)

def to_decimal(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def parse_iso_date(value: str) -> date:
    return datetime.fromisoformat(value).date()


def parse_sunoco_report(file_path: str) -> ParsedReport:
    text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    data = json.loads(text, parse_float=Decimal)

    records = data.get("value", [])

    if not records:
        raise ValueError("SUNOCO report has no records in 'value'.")

    daily_totals = []
    sunoco_credit_card_discounts = []
    settlement_dates = set()

    for item in records:
        location = item.get("location") or {}

        location_id = str(location.get("shipToNumber", "")).strip()
        location_name = str(location.get("shipToCustomerName", "")).strip()

        if not location_id:
            raise ValueError("SUNOCO record missing location.shipToNumber")

        settlement_date = parse_iso_date(item["settlementDate"])
        business_date = settlement_date - timedelta(days=1)


        gross_amt = to_decimal(item.get("totalSalesAmount"))

        # SUNOCO dealer fee comes as negative in JSON, ex. -221.05.
        # Normalized it as positive so validation stays consistent
        dealer_fee = to_decimal(item.get("totalDealerFeeAmount"))
        fees = -dealer_fee

        net_amt = gross_amt - fees

        daily_totals.append(
            DailySettlementTotal(
                supplier="SUNOCO",
                location_id=location_id,
                location_name=location_name,
                date=business_date,
                gross_amt=gross_amt,
                fees=fees,
                net_amt=net_amt,
            )
        )

        discount_amount = to_decimal(item.get("adjustments"))

        sunoco_credit_card_discounts.append(
            SunocoCreditCardDiscount(
                supplier="SUNOCO",
                location_id=location_id,
                location_name=location_name,
                date=business_date,
                amount=discount_amount,
                source_field="adjustments",
            )
        )

        settlement_dates.add(settlement_date)

    daily_totals.sort(key=lambda row: (row.date, row.location_id))

    return ParsedReport(
        supplier="SUNOCO",
        report_date=max(settlement_dates),
        daily_totals=daily_totals,
        mobile_adjustments=[],
        sunoco_credit_card_discounts=sunoco_credit_card_discounts,
    )