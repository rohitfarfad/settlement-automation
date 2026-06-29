import re
from collections import defaultdict
from pathlib import Path

from config.supplier_rules import VALERO_MOBILE_CODES
from settlement_automation.models import (
    DailySettlementTotal,
    MobileAdjustment,
    ParsedReport,
    ValeroPayPlusAdjustment,
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

PAYPLUS_RE = re.compile(
    r"^\s*(\d+)\s+CRND\s+([A-Z0-9]+)\s+VP\+ Fuel Offer\s+"
    r"(\d{2})-(\d{2})\s+([\d,]+\.\d{2}[+-])\s*$"
)


def is_valero_mobile_code(card_code: str) -> bool:
    return card_code in VALERO_MOBILE_CODES or card_code.startswith("VP")


def is_valero_payplus_code(card_code: str) -> bool:
    # The regex already guarantees this is a "VP+ Fuel Offer" row.
    # Do not restrict to VALP/VPAY only, because some valid rows use VISA.
    return True


def parse_valero_mmdd(mmdd: str, report_date):
    """
    Parse Valero MMDD using the report year.

    If a January report contains a prior December transaction,
    this prevents accidentally assigning it to the next December.
    """
    txn_date = parse_mmdd(mmdd, report_date.year)

    if txn_date > report_date:
        txn_date = parse_mmdd(mmdd, report_date.year - 1)

    return txn_date


def find_valero_business_dates_by_location(
    lines: list[str],
    report_date,
) -> dict[str, set]:
    """
    Find true business dates per dealer/location.

    A date is a business date for a specific location only if that same
    dealer block has at least one non-mobile detail row for that date.

    This prevents mobile-only prior-day rows from being treated as daily totals
    just because another location has real business activity on that date.
    """
    business_dates_by_location = defaultdict(set)
    all_sub_dates_by_location = defaultdict(set)

    current_location_id = None
    current_detail_date = None

    for line in lines:
        dealer = DEALER_RE.match(line)

        if dealer:
            current_location_id = dealer.group(1)
            current_detail_date = None
            continue

        if current_location_id is None:
            continue

        sub = SUB_DATE_RE.match(line)

        if sub:
            all_sub_dates_by_location[current_location_id].add(
                parse_valero_mmdd(sub.group(1), report_date)
            )
            continue

        detail = DETAIL_RE.match(line)

        if not detail:
            continue

        mmdd, _, card_code, _, _, _, _, _, _ = detail.groups()

        if mmdd:
            current_detail_date = parse_valero_mmdd(mmdd, report_date)

        if current_detail_date and not is_valero_mobile_code(card_code):
            business_dates_by_location[current_location_id].add(current_detail_date)

    # Fallback per location: if a location has SUB rows but no detail rows matched,
    # preserve old behavior for that location only.
    for location_id, sub_dates in all_sub_dates_by_location.items():
        if location_id not in business_dates_by_location:
            business_dates_by_location[location_id] = sub_dates

    return dict(business_dates_by_location)


def parse_valero_report(file_path: str) -> ParsedReport:
    text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()

    report_date_match = MSR_RE.search(text)

    if not report_date_match:
        raise ValueError("Could not find Valero report date from MSR/DTN line")

    report_date = parse_mmddyy(report_date_match.group(1))

    business_dates_by_location = find_valero_business_dates_by_location(
        lines,
        report_date,
    )

    if not business_dates_by_location:
        raise ValueError("No Valero business dates found")

    daily_totals = []
    mobile_adjustments = []
    valero_pay_plus_adjustments = []

    current_location_id = None
    current_location_name = None
    current_detail_date = None

    locations_by_id = {}

    for line in lines:
        dealer = DEALER_RE.match(line)

        if dealer:
            current_location_id = dealer.group(1)
            current_location_name = dealer.group(2).strip()
            current_detail_date = None
            locations_by_id[current_location_id] = current_location_name
            continue

        # VP+ adjustment rows are outside dealer blocks, near the end of the report.
        payplus = PAYPLUS_RE.match(line)

        if payplus:
            location_id, source_code, month, day, amount = payplus.groups()

            if is_valero_payplus_code(source_code):
                txn_date = parse_valero_mmdd(f"{month}{day}", report_date)

                valero_pay_plus_adjustments.append(
                    ValeroPayPlusAdjustment(
                        supplier="VALERO",
                        location_id=str(location_id),
                        location_name=locations_by_id.get(str(location_id), "UNKNOWN"),
                        date=txn_date,
                        amount=parse_money(amount),
                        source_code=source_code,
                    )
                )

            continue

        if current_location_id is None:
            continue

        location_business_dates = business_dates_by_location.get(
            str(current_location_id),
            set(),
        )

        sub = SUB_DATE_RE.match(line)

        if sub:
            mmdd, _, gross, disc, fee, net = sub.groups()
            txn_date = parse_valero_mmdd(mmdd, report_date)

            if txn_date in location_business_dates:
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
                current_detail_date = parse_valero_mmdd(mmdd, report_date)

            if (
                current_detail_date
                and current_detail_date not in location_business_dates
                and is_valero_mobile_code(card_code)
            ):
                mobile_adjustments.append(
                    MobileAdjustment(
                        supplier="VALERO",
                        location_id=str(current_location_id),
                        location_name=current_location_name,
                        date=current_detail_date,
                        gross_amt=parse_money(gross),
                        fees=-(parse_money(disc) + parse_money(fee)),
                        net_amt=parse_money(net),
                        source_code=card_code,
                    )
                )

    daily_totals.sort(key=lambda row: (row.date, row.location_id))
    mobile_adjustments.sort(
        key=lambda row: (row.date, row.location_id, row.source_code or "")
    )
    valero_pay_plus_adjustments.sort(
        key=lambda row: (row.date, row.location_id, row.source_code or "")
    )

    return ParsedReport(
        supplier="VALERO",
        report_date=report_date,
        daily_totals=daily_totals,
        mobile_adjustments=mobile_adjustments,
        valero_pay_plus_adjustments=valero_pay_plus_adjustments,
    )