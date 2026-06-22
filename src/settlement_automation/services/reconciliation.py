from collections import defaultdict
from decimal import Decimal

from settlement_automation.models import MobileAdjustment


def summarize_mobile_adjustments(
    rows: list[MobileAdjustment],
) -> list[MobileAdjustment]:
    grouped = defaultdict(lambda: {
        "gross_amt": Decimal("0.00"),
        "fees": Decimal("0.00"),
        "net_amt": Decimal("0.00"),
    })

    metadata = {}

    for row in rows:
        key = (row.supplier, row.location_id, row.location_name, row.date)

        metadata[key] = row

        grouped[key]["gross_amt"] += row.gross_amt
        grouped[key]["fees"] += row.fees
        grouped[key]["net_amt"] += row.net_amt

    summary = []

    for key, amounts in grouped.items():
        supplier, location_id, location_name, txn_date = key

        summary.append(
            MobileAdjustment(
                supplier=supplier,
                location_id=location_id,
                location_name=location_name,
                date=txn_date,
                gross_amt=amounts["gross_amt"],
                fees=amounts["fees"],
                net_amt=amounts["net_amt"],
                source_code="TOTAL",
            )
        )

    return sorted(summary, key=lambda x: (x.date, x.location_id))


def get_mobile_adjustment_grand_total(
    rows: list[MobileAdjustment],
) -> tuple[Decimal, Decimal, Decimal]:
    gross = sum((row.gross_amt for row in rows), Decimal("0.00"))
    fees = sum((row.fees for row in rows), Decimal("0.00"))
    net = sum((row.net_amt for row in rows), Decimal("0.00"))

    return gross, fees, net