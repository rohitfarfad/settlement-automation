from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Optional, Sequence

from config.supplier_accounts import (
    SupplierAccount,
    get_active_supplier_accounts,
    get_supplier_account,
)
from settlement_automation.connectors import get_connector
from settlement_automation.connectors.base import SupplierPortalConnector
from settlement_automation.connectors.download_manager import (
    DownloadManager,
    StoredRawReport,
)


ConnectorFactory = Callable[[SupplierAccount], SupplierPortalConnector]


@dataclass(frozen=True)
class FetchResult:
    supplier_name: str
    portal_name: str
    business_date: date
    status: str
    downloaded_files: list[Path]
    stored_reports: list[StoredRawReport]
    error_message: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        return self.status == "success"

    @property
    def raw_paths(self) -> list[Path]:
        return [report.raw_path for report in self.stored_reports]


def fetch_reports_for_account(
    account: SupplierAccount,
    business_date: date,
    download_manager: Optional[DownloadManager] = None,
    connector_factory: ConnectorFactory = get_connector,
    remove_downloaded_files: bool = True,
    raise_on_error: bool = False,
) -> FetchResult:
    """
    Fetch reports for one supplier account and store them in standardized raw storage.

    This function intentionally does not parse, validate, reconcile, or write Excel.
    """
    manager = download_manager or DownloadManager()

    try:
        connector = connector_factory(account)

        downloaded_files = connector.fetch_reports(business_date)

        stored_reports = [
            manager.store_raw_report(
                source_path=downloaded_file,
                account=account,
                business_date=business_date,
                remove_source=remove_downloaded_files,
            )
            for downloaded_file in downloaded_files
        ]

        return FetchResult(
            supplier_name=account.supplier_name,
            portal_name=account.portal_name,
            business_date=business_date,
            status="success",
            downloaded_files=downloaded_files,
            stored_reports=stored_reports,
        )

    except Exception as exc:
        if raise_on_error:
            raise

        return FetchResult(
            supplier_name=account.supplier_name,
            portal_name=account.portal_name,
            business_date=business_date,
            status="failed",
            downloaded_files=[],
            stored_reports=[],
            error_message=str(exc),
        )


def resolve_supplier_accounts(
    supplier_names: Optional[Sequence[str]] = None,
) -> list[SupplierAccount]:
    if supplier_names:
        return [get_supplier_account(name) for name in supplier_names]

    return get_active_supplier_accounts()


def fetch_reports_for_suppliers(
    business_date: date,
    supplier_names: Optional[Sequence[str]] = None,
    download_manager: Optional[DownloadManager] = None,
    connector_factory: ConnectorFactory = get_connector,
    remove_downloaded_files: bool = True,
) -> list[FetchResult]:
    """
    Fetch reports for selected suppliers or all active suppliers.

    One supplier failure should not stop the remaining suppliers.
    """
    accounts = resolve_supplier_accounts(supplier_names)

    return [
        fetch_reports_for_account(
            account=account,
            business_date=business_date,
            download_manager=download_manager,
            connector_factory=connector_factory,
            remove_downloaded_files=remove_downloaded_files,
            raise_on_error=False,
        )
        for account in accounts
    ]