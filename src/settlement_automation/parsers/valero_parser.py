import re
from dataclasses import dataclass, field
from datetime import date, timedelta
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

SUB_KIND_RE = re.compile(
    r"^\s*SUB\s+(POS|CRIND)\s+(\d+)\s+"
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

@dataclass
class ValeroDateBlockStats:
    location_id: str
    txn_date: date
    has_final_sub: bool = False
    final_sub_count: int = 0
    has_sub_pos: bool = False
    has_sub_crind: bool = False
    detail_rows: int = 0
    normal_detail_rows: int = 0
    normal_card_codes: set[str] = field(default_factory=set)
    normal_pos_card_codes: set[str] = field(default_factory=set)


def _get_date_block_stats(
    blocks: dict[tuple[str, date], ValeroDateBlockStats],
    location_id: str,
    txn_date: date,
) -> ValeroDateBlockStats:
    key = (location_id, txn_date)

    if key not in blocks:
        blocks[key] = ValeroDateBlockStats(
            location_id=location_id,
            txn_date=txn_date,
        )

    return blocks[key]


def collect_valero_date_block_stats(
    lines: list[str],
    report_date,
) -> dict[tuple[str, date], ValeroDateBlockStats]:
    """
    Collect per-location/per-date structure.

    This lets us distinguish:
    - full late daily settlement blocks
    - small backdated/mobile-only blocks
    """
    blocks: dict[tuple[str, date], ValeroDateBlockStats] = {}

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

        detail = DETAIL_RE.match(line)

        if detail:
            mmdd, io_type, card_code, _, _, _, _, _, _ = detail.groups()

            if mmdd:
                current_detail_date = parse_valero_mmdd(mmdd, report_date)

            if current_detail_date:
                stats = _get_date_block_stats(
                    blocks,
                    str(current_location_id),
                    current_detail_date,
                )

                stats.detail_rows += 1

                if not is_valero_mobile_code(card_code):
                    stats.normal_detail_rows += 1
                    stats.normal_card_codes.add(card_code)

                    if io_type == "POS":
                        stats.normal_pos_card_codes.add(card_code)

            continue

        sub_kind = SUB_KIND_RE.match(line)

        if sub_kind and current_detail_date:
            kind = sub_kind.group(1)

            stats = _get_date_block_stats(
                blocks,
                str(current_location_id),
                current_detail_date,
            )

            if kind == "POS":
                stats.has_sub_pos = True
            elif kind == "CRIND":
                stats.has_sub_crind = True

            continue

        sub = SUB_DATE_RE.match(line)

        if sub:
            txn_date = parse_valero_mmdd(sub.group(1), report_date)

            stats = _get_date_block_stats(
                blocks,
                str(current_location_id),
                txn_date,
            )

            stats.has_final_sub = True
            stats.final_sub_count = int(sub.group(2))

    return blocks


def looks_like_late_full_daily_settlement(stats: ValeroDateBlockStats) -> bool:
    """
    Promote an older/non-expected date to daily_totals only when it looks like
    a complete store settlement block.

    This catches cases like Fishkill 0708 in the 07/10 report, while keeping
    small VP/mobile-only prior-date blocks as mobile_adjustments.
    """
    if not stats.has_final_sub:
        return False

    # Strong full-day signal:
    # a POS section plus multiple normal/non-VP POS card types.
    if (
        stats.has_sub_pos
        and stats.normal_detail_rows >= 4
        and len(stats.normal_pos_card_codes) >= 2
    ):
        return True

    # Full POS + CRIND daily block, even if POS card variety is small.
    if (
        stats.has_sub_pos
        and stats.has_sub_crind
        and stats.normal_detail_rows >= 5
        and len(stats.normal_card_codes) >= 3
    ):
        return True

    # Some stores/days can be CRIND-heavy. Allow large CRIND-only full days,
    # but avoid tiny CRND VP-only mobile blocks.
    if (
        stats.has_sub_crind
        and stats.final_sub_count >= 20
        and stats.normal_detail_rows >= 5
        and len(stats.normal_card_codes) >= 3
    ):
        return True

    return False


def find_valero_daily_dates_by_location(
    lines: list[str],
    report_date,
    expected_settlement_dates: set[date],
) -> dict[str, set[date]]:
    """
    Return dates that should be parsed as DailySettlementTotal per location.

    Expected report dates are always daily.
    Older dates are daily only if the specific location/date block looks like
    a complete settlement block.
    """
    blocks = collect_valero_date_block_stats(lines, report_date)

    daily_dates_by_location: dict[str, set[date]] = {}

    for (location_id, txn_date), stats in blocks.items():
        if not stats.has_final_sub:
            continue

        if (
            txn_date in expected_settlement_dates
            or looks_like_late_full_daily_settlement(stats)
        ):
            daily_dates_by_location.setdefault(location_id, set()).add(txn_date)

    return daily_dates_by_location

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

    expected_settlement_dates = get_valero_settlement_dates(
        report_date=report_date,
        available_sub_dates=available_sub_dates,
    )

    if not expected_settlement_dates:
        raise ValueError("No Valero settlement dates found")

    daily_dates_by_location = find_valero_daily_dates_by_location(
        lines=lines,
        report_date=report_date,
        expected_settlement_dates=expected_settlement_dates,
    )

    if not daily_dates_by_location:
        raise ValueError("No Valero daily settlement dates found")

    monthly_charge_date = max(expected_settlement_dates)

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

            location_daily_dates = daily_dates_by_location.get(
                str(current_location_id),
                set(),
            )

            if txn_date in location_daily_dates:
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

            location_daily_dates = daily_dates_by_location.get(
                str(current_location_id),
                set(),
            )

            # Any detail row from a date that is not daily for this specific location
            # remains a backdated/mobile adjustment.
            #
            # This keeps South Plank 0708 as mobile, but prevents Fishkill 0708 from
            # being added to mobile because Fishkill 0708 is now classified as a full
            # late daily settlement block.
            if current_detail_date and current_detail_date not in location_daily_dates:
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