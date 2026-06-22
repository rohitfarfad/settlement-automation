import pytest

from config.supplier_accounts import (
    get_active_supplier_accounts,
    get_supplier_account,
)
from settlement_automation.connectors import get_connector
from settlement_automation.connectors.dtn_portal import DTNPortalConnector
from settlement_automation.connectors.sunoco_portal import SunocoPortalConnector


def test_active_supplier_accounts_include_expected_suppliers():
    accounts = get_active_supplier_accounts()
    supplier_names = {account.supplier_name for account in accounts}

    assert "sunoco" in supplier_names
    assert "citgo" in supplier_names
    assert "valero" in supplier_names


def test_sunoco_uses_sunoco_connector():
    account = get_supplier_account("sunoco")
    connector = get_connector(account)

    assert isinstance(connector, SunocoPortalConnector)
    assert connector.account.supplier_name == "sunoco"
    assert connector.account.portal_name == "sunoco"


def test_citgo_uses_dtn_connector():
    account = get_supplier_account("citgo")
    connector = get_connector(account)

    assert isinstance(connector, DTNPortalConnector)
    assert connector.account.supplier_name == "citgo"
    assert connector.account.portal_name == "dtn"


def test_valero_uses_dtn_connector():
    account = get_supplier_account("valero")
    connector = get_connector(account)

    assert isinstance(connector, DTNPortalConnector)
    assert connector.account.supplier_name == "valero"
    assert connector.account.portal_name == "dtn"


def test_unknown_supplier_raises_error():
    with pytest.raises(ValueError):
        get_supplier_account("unknown")