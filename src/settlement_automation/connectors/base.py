from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path

from config.supplier_accounts import SupplierAccount


class SupplierPortalConnector(ABC):
    def __init__(self, account: SupplierAccount):
        self.account = account

    @abstractmethod
    def fetch_reports(self, business_date: date) -> list[Path]:
        """
        Download report files for the given business date.

        Returns local downloaded file paths, usually from data/tmp/.
        The caller is responsible for storing those files into standardized
        raw storage using DownloadManager.

        This method should not parse, validate, reconcile, or write Excel output.
        """
        raise NotImplementedError