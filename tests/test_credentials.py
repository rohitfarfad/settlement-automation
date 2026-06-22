import pytest

from config.supplier_accounts import get_supplier_account
from settlement_automation.connectors.credentials import load_credentials
from settlement_automation.exceptions import MissingCredentialsError


def test_load_sunoco_credentials(monkeypatch):
    account = get_supplier_account("sunoco")

    monkeypatch.setenv("SUNOCO_USERNAME", "sunoco_user")
    monkeypatch.setenv("SUNOCO_PASSWORD", "sunoco_password")

    credentials = load_credentials(account)

    assert credentials.supplier_name == "sunoco"
    assert credentials.portal_name == "sunoco"
    assert credentials.username == "sunoco_user"
    assert credentials.password == "sunoco_password"
    assert credentials.username_env == "SUNOCO_USERNAME"
    assert credentials.password_env == "SUNOCO_PASSWORD"


def test_load_citgo_dtn_credentials(monkeypatch):
    account = get_supplier_account("citgo")

    monkeypatch.setenv("DTN_USERNAME", "dtn_user")
    monkeypatch.setenv("DTN_PASSWORD", "dtn_password")

    credentials = load_credentials(account)

    assert credentials.supplier_name == "citgo"
    assert credentials.portal_name == "dtn"
    assert credentials.username == "dtn_user"
    assert credentials.password == "dtn_password"


def test_load_valero_dtn_credentials(monkeypatch):
    account = get_supplier_account("valero")

    monkeypatch.setenv("DTN_USERNAME", "dtn_user")
    monkeypatch.setenv("DTN_PASSWORD", "dtn_password")

    credentials = load_credentials(account)

    assert credentials.supplier_name == "valero"
    assert credentials.portal_name == "dtn"
    assert credentials.username == "dtn_user"
    assert credentials.password == "dtn_password"


def test_missing_credentials_raises_clear_error(monkeypatch):
    account = get_supplier_account("citgo")

    monkeypatch.delenv("DTN_USERNAME", raising=False)
    monkeypatch.delenv("DTN_PASSWORD", raising=False)

    with pytest.raises(MissingCredentialsError) as exc_info:
        load_credentials(account)

    error_message = str(exc_info.value)

    assert "supplier=citgo" in error_message
    assert "portal=dtn" in error_message
    assert "DTN_USERNAME" in error_message
    assert "DTN_PASSWORD" in error_message


def test_password_is_not_exposed_in_repr(monkeypatch):
    account = get_supplier_account("valero")

    monkeypatch.setenv("DTN_USERNAME", "dtn_user")
    monkeypatch.setenv("DTN_PASSWORD", "super_secret_password")

    credentials = load_credentials(account)

    assert "super_secret_password" not in repr(credentials)