import re
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from config.locations import CITGO_LOCATIONS
from settlement_automation.models import DailySettlementTotal, ParsedReport
from settlement_automation.utils.dates import parse_mmdd, parse_mmddyy
from settlement_automation.utils.money import parse_money


REPORT_DATE_RE = re.compile(r"CIT1\s+\d+\s+\S+\s+(\d{2}-\d{2}-\d{2})\s+START MSG")

DETAIL_ROW_RE = re.compile(
    r"^\s*(\d{8})\s+"          # location
    r"(\d{2})\s+"              # term
    r"(\d{2})\s+"              # batch
    r"(\d{4})\s+"              # date MMDD
    r"(\d+)\s+"                # count
    r"([A-Z/]+)\s+"            # type
    r"([\d,]+\.\d{2})\s+"      # gross
    r"([\d,]+\.\d{2})\s+"      # fees
    r"([\d,]+\.\d{2})"         # net
)


def parse_citgo_report(file_path: str) -> ParsedReport:
    text = Path(file_path).read_text(encoding="utf-8", errors="ignore")

    report_date_match = REPORT_DATE_RE.search(text)
    if not report_date_match:
        raise ValueError("Could not find CITGO report date from START MSG line")

    report_date = parse_mmddyy(report_date_match.group(1))
    year = report_date.year

    totals = defaultdict(lambda: {
        "gross_amt": Decimal("0.00"),
        "fees": Decimal("0.00"),
        "net_amt": Decimal("0.00"),
    })

    for line in text.splitlines():
        match = DETAIL_ROW_RE.match(line)
        if not match:
            continue

        location_id, _, _, mmdd, _, _, gross, fees, net = match.groups()

        location_id = str(location_id)
        txn_date = parse_mmdd(mmdd, year)

        key = (location_id, txn_date)

        totals[key]["gross_amt"] += parse_money(gross)
        totals[key]["fees"] += parse_money(fees)
        totals[key]["net_amt"] += parse_money(net)

    daily_totals = []

    for (location_id, txn_date), amounts in totals.items():
        daily_totals.append(
            DailySettlementTotal(
                supplier="CITGO",
                location_id=location_id,
                location_name=CITGO_LOCATIONS.get(location_id, "UNKNOWN"),
                date=txn_date,
                gross_amt=amounts["gross_amt"],
                fees=amounts["fees"],
                net_amt=amounts["net_amt"],
            )
        )

    daily_totals.sort(key=lambda row: (row.date, row.location_id))

    return ParsedReport(
        supplier="CITGO",
        report_date=report_date,
        daily_totals=daily_totals,
        mobile_adjustments=[],
    )