import os
from dataclasses import dataclass, field

from config.supplier_accounts import SupplierAccount
from settlement_automation.exceptions import MissingCredentialsError


@dataclass(frozen=True)
class PortalCredentials:
    supplier_name: str
    portal_name: str
    username: str
    password: str = field(repr=False)
    username_env: str = ""
    password_env: str = ""

    @property
    def safe_display_name(self) -> str:
        return f"{self.portal_name}:{self.supplier_name}:{self.username}"


def load_credentials(account: SupplierAccount) -> PortalCredentials:
    username = os.getenv(account.username_env)
    password = os.getenv(account.password_env)

    missing = []

    if username is None or username.strip() == "":
        missing.append(account.username_env)

    if password is None or password.strip() == "":
        missing.append(account.password_env)

    if missing:
        missing_vars = ", ".join(missing)
        raise MissingCredentialsError(
            f"Missing credentials for supplier={account.supplier_name}, "
            f"portal={account.portal_name}. Missing env vars: {missing_vars}"
        )

    return PortalCredentials(
        supplier_name=account.supplier_name,
        portal_name=account.portal_name,
        username=username.strip(),
        password=password.strip(),
        username_env=account.username_env,
        password_env=account.password_env,
    )