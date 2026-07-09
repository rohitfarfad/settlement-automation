from settlement_automation.models import MobileAdjustment, ValeroPayPlusAdjustment
from settlement_automation.models import ValeroMonthlyCharge
from settlement_automation.models import SunocoCreditCardDiscount

from collections import defaultdict
from decimal import Decimal


def summarize_valero_monthly_charges(
    rows: list[ValeroMonthlyCharge],
) -> list[ValeroMonthlyCharge]:
    grouped = defaultdict(lambda: Decimal("0.00"))
    names = {}

    for row in rows:
        key = (row.supplier, row.location_id, row.location_name, row.date)
        grouped[key] += row.amount
        names[key] = row.location_name

    summary = []

    for key, amount in grouped.items():
        supplier, location_id, location_name, txn_date = key

        summary.append(
            ValeroMonthlyCharge(
                supplier=supplier,
                location_id=location_id,
                location_name=location_name,
                date=txn_date,
                amount=amount,
                description="MONTHLY CHARGES TOTAL",
            )
        )

    return sorted(summary, key=lambda row: (row.date, row.location_id))


def get_valero_monthly_charges_grand_total(
    rows: list[ValeroMonthlyCharge],
) -> Decimal:
    return sum((row.amount for row in rows), Decimal("0.00"))

def summarize_mobile_adjustments(
    rows: list[MobileAdjustment],
) -> list[MobileAdjustment]:
    grouped = defaultdict(lambda: {
        "gross_amt": Decimal("0.00"),
        "fees": Decimal("0.00"),
        "net_amt": Decimal("0.00"),
    })

    for row in rows:
        key = (row.supplier, row.location_id, row.location_name, row.date)

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


def summarize_valero_pay_plus_adjustments(
    rows: list[ValeroPayPlusAdjustment],
) -> list[ValeroPayPlusAdjustment]:
    grouped = defaultdict(lambda: Decimal("0.00"))
    metadata = {}

    for row in rows:
        key = (row.supplier, row.location_id, row.location_name, row.date)
        metadata[key] = row
        grouped[key] += row.amount

    summary = []

    for key, amount in grouped.items():
        supplier, location_id, location_name, txn_date = key

        summary.append(
            ValeroPayPlusAdjustment(
                supplier=supplier,
                location_id=location_id,
                location_name=location_name,
                date=txn_date,
                amount=amount,
                source_code="TOTAL",
            )
        )

    return sorted(summary, key=lambda x: (x.date, x.location_id))


def get_valero_pay_plus_grand_total(
    rows: list[ValeroPayPlusAdjustment],
) -> Decimal:
    return sum((row.amount for row in rows), Decimal("0.00"))

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


def summarize_sunoco_credit_card_discounts(
    rows: list[SunocoCreditCardDiscount],
) -> list[SunocoCreditCardDiscount]:
    grouped = defaultdict(lambda: Decimal("0.00"))

    for row in rows:
        key = (row.supplier, row.location_id, row.location_name, row.date)
        grouped[key] += row.amount

    summary = []

    for key, amount in grouped.items():
        supplier, location_id, location_name, txn_date = key

        summary.append(
            SunocoCreditCardDiscount(
                supplier=supplier,
                location_id=location_id,
                location_name=location_name,
                date=txn_date,
                amount=amount,
                source_field="adjustments",
            )
        )

    return sorted(summary, key=lambda row: (row.date, row.location_id))


def get_sunoco_credit_card_discounts_grand_total(
    rows: list[SunocoCreditCardDiscount],
) -> Decimal:
    return sum((row.amount for row in rows), Decimal("0.00"))