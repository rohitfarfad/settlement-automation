import re
from pathlib import Path

from config.supplier_rules import VALERO_MOBILE_CODES
from settlement_automation.models import (
    DailySettlementTotal,
    MobileAdjustment,
    ParsedReport,
)
from settlement_automation.utils.dates import parse_mmdd, parse_mmddyy
from settlement_automation.utils.money import parse_money


DEALER_RE = re.compile(r"^\s*DEALER\s+(\d+)\s+(.+?)\s*$")
MSR_RE = re.compile(r"MSR/DTN:\s+(\d{2}/\d{2}/\d{2})")

SUB_DATE_RE = re.compile(
    r"^\s*SUB\s+(\d{4})\s+(\d+)\s+"
    r"([\d,]+\.\d{2}[+-])\s+"
    r"([\d,]+\.\d{2}[+-])\s+"
    r"([\d,]+\.\d{2}[+-])\s+"
    r"([\d,]+\.\d{2}[+-])"
)

DETAIL_RE = re.compile(
    r"^\s*(?:(\d{4})\s+)?"
    r"(POS|CRND)\s+([A-Z0-9]+)\s+([A-Z]+)\s+(\d+)\s+"
    r"([\d,]+\.\d{2}[+-])\s+"
    r"([\d,]+\.\d{2}[+-])\s+"
    r"([\d,]+\.\d{2}[+-])\s+"
    r"([\d,]+\.\d{2}[+-])"
)


def parse_valero_report(file_path: str) -> ParsedReport:
    text = Path(file_path).read_text(encoding="utf-8", errors="ignore")

    report_date_match = MSR_RE.search(text)
    if not report_date_match:
        raise ValueError("Could not find Valero report date from MSR/DTN line")

    report_date = parse_mmddyy(report_date_match.group(1))
    year = report_date.year

    sub_dates = []
    for line in text.splitlines():
        match = SUB_DATE_RE.match(line)
        if match:
            sub_dates.append(parse_mmdd(match.group(1), year))

    if not sub_dates:
        raise ValueError("No Valero SUB date totals found")

    current_business_date = max(sub_dates)

    daily_totals = []
    mobile_adjustments = []

    current_location_id = None
    current_location_name = None
    current_detail_date = None

    for line in text.splitlines():
        dealer = DEALER_RE.match(line)

        if dealer:
            current_location_id = int(dealer.group(1))
            current_location_name = dealer.group(2).strip()
            current_detail_date = None
            continue

        if current_location_id is None:
            continue

        sub = SUB_DATE_RE.match(line)

        if sub:
            mmdd, _, gross, disc, fee, net = sub.groups()
            txn_date = parse_mmdd(mmdd, year)

            if txn_date == current_business_date:
                daily_totals.append(
                    DailySettlementTotal(
                        supplier="VALERO",
                        location_id=str(current_location_id),
                        location_name=current_location_name,
                        date=txn_date,
                        gross_amt=parse_money(gross),
                        fees=-(parse_money(disc) + parse_money(fee)),
                        net_amt=parse_money(net),
                    )
                )

            continue

        detail = DETAIL_RE.match(line)

        if detail:
            mmdd, _, card_code, _, _, gross, disc, fee, net = detail.groups()

            if mmdd:
                current_detail_date = parse_mmdd(mmdd, year)

            if (
                current_detail_date
                and current_detail_date < current_business_date
                and card_code in VALERO_MOBILE_CODES
            ):
                mobile_adjustments.append(
                    MobileAdjustment(
                        supplier="VALERO",
                        location_id=current_location_id,
                        location_name=current_location_name,
                        date=current_detail_date,
                        gross_amt=parse_money(gross),
                        fees=-(parse_money(disc) + parse_money(fee)),
                        net_amt=parse_money(net),
                        source_code=card_code,
                    )
                )

    return ParsedReport(
        supplier="VALERO",
        report_date=report_date,
        daily_totals=daily_totals,
        mobile_adjustments=mobile_adjustments,
    )