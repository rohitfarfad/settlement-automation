import re
from datetime import timedelta
from pathlib import Path

from config.supplier_rules import VALERO_MOBILE_CODES
from settlement_automation.models import (
    DailySettlementTotal,
    MobileAdjustment,
    ParsedReport,
    UnclassifiedAdjustment,
    ValeroPayPlusAdjustment,
    ValeroMonthlyCharge,
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
    r"([A-Z]+)\s+([A-Z0-9]+)\s+([A-Z]+)\s+(\d+)\s+"
    r"([\d,]+\.\d{2}[+-])\s+"
    r"([\d,]+\.\d{2}[+-])\s+"
    r"([\d,]+\.\d{2}[+-])\s+"
    r"([\d,]+\.\d{2}[+-])"
)

PAYPLUS_RE = re.compile(
    r"^\s*(\d+)\s+CRND\s+([A-Z0-9]+)\s+VP\+ Fuel Offer\s+"
    r"(\d{2})-(\d{2})\s+([\d,]+\.\d{2}[+-])\s*$"
)

MONTHLY_CHARGE_RE = re.compile(
    r"^\s*(\d+)\s+MONTHLY\s+(.+?)\s+BILLING\s+([\d,]+\.\d{2}[+-])\s*$",
    re.IGNORECASE,
)

ADJUSTMENTS_SECTION_RE = re.compile(r"^\s*ADJUSTMENTS\s*$", re.IGNORECASE)

TOTAL_ADJUSTMENTS_RE = re.compile(
    r"^\s*TOTAL\s+ADJUSTMENTS\b",
    re.IGNORECASE,
)

ADJUSTMENT_HEADER_RE = re.compile(
    r"^\s*DEALER\s+DESCRIPTION\s+ADJUSTMENT\s+AMT\s*$",
    re.IGNORECASE,
)

UNCLASSIFIED_ADJUSTMENT_RE = re.compile(
    r"^\s*(\d{5})\s+(.+?)\s+([\d,]+\.\d{2}[+-])\s*$"
)

def is_valero_mobile_code(card_code: str) -> bool:
    return card_code in VALERO_MOBILE_CODES or card_code.startswith("VP")


def is_valero_payplus_code(card_code: str) -> bool:
    # PAYPLUS_RE already guarantees this is a "VP+ Fuel Offer" row.
    # Do not restrict to VALP/VPAY only because some valid rows use VISA.
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


def collect_valero_sub_dates(lines: list[str], report_date) -> set:
    sub_dates = set()

    for line in lines:
        sub = SUB_DATE_RE.match(line)

        if sub:
            sub_dates.add(parse_valero_mmdd(sub.group(1), report_date))

    return sub_dates


def get_valero_settlement_dates(report_date, available_sub_dates: set) -> set:
    """
    Valero normally reports the previous business day's settlement.

    Monday reports include the weekend batch:
    Friday, Saturday, and Sunday.

    Older dates in the same report are treated as backdated/mobile
    adjustments, not new daily totals.
    """
    if report_date.weekday() == 0:  # Monday
        expected_dates = {
            report_date - timedelta(days=3),
            report_date - timedelta(days=2),
            report_date - timedelta(days=1),
        }
    else:
        expected_dates = {
            report_date - timedelta(days=1),
        }

    matched_dates = expected_dates & available_sub_dates

    if matched_dates:
        return matched_dates

    # Safe fallback: if the expected calendar rule fails, parse the latest
    # prior date only instead of treating all older dates as daily totals.
    prior_dates = {d for d in available_sub_dates if d < report_date}

    if prior_dates:
        return {max(prior_dates)}

    return set()

def parse_valero_charge_amount(value: str):
    """
    Monthly charge rows are shown as negative amounts in the report,
    for example 113.53-.

    Store them as positive fee amounts so Excel can add them to CC FEE.
    """
    return abs(parse_money(value))

def parse_unclassified_adjustment_amount(value: str):
    try:
        return parse_money(value)
    except Exception:
        return None

def parse_valero_report(file_path: str) -> ParsedReport:
    text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()

    report_date_match = MSR_RE.search(text)

    if not report_date_match:
        raise ValueError("Could not find Valero report date from MSR/DTN line")

    report_date = parse_mmddyy(report_date_match.group(1))

    available_sub_dates = collect_valero_sub_dates(lines, report_date)
    settlement_dates = get_valero_settlement_dates(
        report_date=report_date,
        available_sub_dates=available_sub_dates,
    )

    if not settlement_dates:
        raise ValueError("No Valero settlement dates found")

    monthly_charge_date = max(settlement_dates)

    daily_totals = []
    mobile_adjustments = []
    valero_pay_plus_adjustments = []
    valero_monthly_charges = []
    unclassified_adjustments = []

    current_location_id = None
    current_location_name = None
    current_detail_date = None

    locations_by_id = {}
    in_adjustments_section = False
    for line in lines:
        if ADJUSTMENTS_SECTION_RE.match(line):
            in_adjustments_section = True
            continue

        if in_adjustments_section:
            if TOTAL_ADJUSTMENTS_RE.match(line):
                in_adjustments_section = False
                continue

            if not line.strip() or ADJUSTMENT_HEADER_RE.match(line):
                continue

            payplus = PAYPLUS_RE.match(line)
            if payplus:
                location_id, source_code, month, day, amount = payplus.groups()

                if is_valero_payplus_code(source_code):
                    txn_date = parse_valero_mmdd(f"{month}{day}", report_date)

                    valero_pay_plus_adjustments.append(
                        ValeroPayPlusAdjustment(
                            supplier="VALERO",
                            location_id=str(location_id),
                            location_name=locations_by_id.get(
                                str(location_id),
                                "UNKNOWN",
                            ),
                            date=txn_date,
                            amount=parse_money(amount),
                            source_code=source_code,
                        )
                    )

                continue

            monthly_charge = MONTHLY_CHARGE_RE.match(line)
            if monthly_charge:
                location_id, description, amount = monthly_charge.groups()
                location_id = str(location_id)

                valero_monthly_charges.append(
                    ValeroMonthlyCharge(
                        supplier="VALERO",
                        location_id=location_id,
                        location_name=locations_by_id.get(location_id, "UNKNOWN"),
                        date=monthly_charge_date,
                        amount=parse_valero_charge_amount(amount),
                        description=f"MONTHLY {description.strip()} BILLING",
                    )
                )

                continue

            unclassified = UNCLASSIFIED_ADJUSTMENT_RE.match(line)
            if unclassified:
                location_id, description, amount = unclassified.groups()
                location_id = str(location_id)

                unclassified_adjustments.append(
                    UnclassifiedAdjustment(
                        supplier="VALERO",
                        location_id=location_id,
                        location_name=locations_by_id.get(location_id, "UNKNOWN"),
                        report_date=report_date,
                        amount=parse_unclassified_adjustment_amount(amount),
                        description=description.strip(),
                        raw_line=line.rstrip(),
                    )
                )

                continue

            continue

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

        sub = SUB_DATE_RE.match(line)

        if sub:
            mmdd, _, gross, disc, fee, net = sub.groups()
            txn_date = parse_valero_mmdd(mmdd, report_date)

            if txn_date in settlement_dates:
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

            # Any detail row from a non-settlement date is a backdated adjustment.
            # This intentionally includes old-date non-VP rows like POS DBT,
            # because they are part of the backdated amount that must be added
            # to an existing Excel row instead of overwriting it.
            if current_detail_date and current_detail_date not in settlement_dates:
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

    valero_monthly_charges.sort(
        key=lambda row: (row.date, row.location_id, row.description)
    )
    unclassified_adjustments.sort(
        key=lambda row: (
            row.report_date,
            row.location_id or "",
            row.description,
            row.raw_line,
        )
    )

    return ParsedReport(
        supplier="VALERO",
        report_date=report_date,
        daily_totals=daily_totals,
        mobile_adjustments=mobile_adjustments,
        valero_pay_plus_adjustments=valero_pay_plus_adjustments,
        valero_monthly_charges=valero_monthly_charges,
        unclassified_adjustments=unclassified_adjustments,
    )