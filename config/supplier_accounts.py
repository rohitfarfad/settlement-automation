from dataclasses import dataclass


@dataclass(frozen=True)
class SupplierAccount:
    supplier_name: str
    portal_name: str
    username_env: str
    password_env: str
    parser_name: str
    report_format: str
    active: bool = True


SUPPLIER_ACCOUNTS = [
    SupplierAccount(
        supplier_name="sunoco",
        portal_name="sunoco",
        username_env="SUNOCO_USERNAME",
        password_env="SUNOCO_PASSWORD",
        parser_name="sunoco",
        report_format="json",
    ),
    SupplierAccount(
        supplier_name="citgo",
        portal_name="dtn",
        username_env="DTN_USERNAME",
        password_env="DTN_PASSWORD",
        parser_name="citgo",
        report_format="txt",
    ),
    SupplierAccount(
        supplier_name="valero",
        portal_name="dtn",
        username_env="DTN_USERNAME",
        password_env="DTN_PASSWORD",
        parser_name="valero",
        report_format="txt",
    ),
]


def get_active_supplier_accounts() -> list[SupplierAccount]:
    return [account for account in SUPPLIER_ACCOUNTS if account.active]


def get_supplier_account(supplier_name: str) -> SupplierAccount:
    for account in SUPPLIER_ACCOUNTS:
        if account.supplier_name == supplier_name.lower():
            return account

    raise ValueError(f"Unsupported supplier: {supplier_name}")