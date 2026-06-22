from config.supplier_accounts import SupplierAccount
from settlement_automation.connectors.dtn_portal import DTNPortalConnector
from settlement_automation.connectors.sunoco_portal import SunocoPortalConnector
from settlement_automation.connectors.base import SupplierPortalConnector


def get_connector(account: SupplierAccount) -> SupplierPortalConnector:
    if account.portal_name == "sunoco":
        return SunocoPortalConnector(account)

    if account.portal_name == "dtn":
        return DTNPortalConnector(account)

    raise ValueError(
        f"Unsupported portal={account.portal_name} for supplier={account.supplier_name}"
    )