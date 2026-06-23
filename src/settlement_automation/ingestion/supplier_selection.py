from collections import defaultdict
from dataclasses import dataclass

from config.supplier_accounts import get_supplier_account


SUPPORTED_SUPPLIERS = ("citgo", "valero", "sunoco")


@dataclass(frozen=True)
class SupplierGroup:
    portal_name: str
    supplier_names: list[str]


def parse_supplier_selection(value: str) -> list[str]:
    """
    Parse supplier selection.

    Supported examples:
        citgo
        valero
        sunoco
        citgo,valero
        dtn
        all
    """
    normalized = value.strip().lower()

    if normalized == "all":
        return ["citgo", "valero", "sunoco"]

    if normalized == "dtn":
        return ["citgo", "valero"]

    selected = []

    for part in normalized.split(","):
        supplier = part.strip().lower()

        if not supplier:
            continue

        if supplier not in SUPPORTED_SUPPLIERS:
            expected = ", ".join(SUPPORTED_SUPPLIERS)
            raise ValueError(
                f"Unsupported supplier '{supplier}'. "
                f"Expected one of: {expected}, dtn, all"
            )

        if supplier not in selected:
            selected.append(supplier)

    if not selected:
        raise ValueError("At least one supplier must be selected.")

    return selected


def group_suppliers_by_portal(supplier_names: list[str]) -> list[SupplierGroup]:
    """
    Group selected suppliers by portal.

    Example:
        ["citgo", "valero", "sunoco"]

    returns:
        [
            SupplierGroup(portal_name="dtn", supplier_names=["citgo", "valero"]),
            SupplierGroup(portal_name="sunoco", supplier_names=["sunoco"]),
        ]
    """
    grouped = defaultdict(list)

    for supplier_name in supplier_names:
        account = get_supplier_account(supplier_name)
        grouped[account.portal_name].append(account.supplier_name)

    # Keep deterministic portal order for readable logs.
    portal_order = ["dtn", "sunoco"]

    result = []

    for portal_name in portal_order:
        if portal_name in grouped:
            result.append(
                SupplierGroup(
                    portal_name=portal_name,
                    supplier_names=grouped[portal_name],
                )
            )

    for portal_name in sorted(grouped):
        if portal_name not in portal_order:
            result.append(
                SupplierGroup(
                    portal_name=portal_name,
                    supplier_names=grouped[portal_name],
                )
            )

    return result