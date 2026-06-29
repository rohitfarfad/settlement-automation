import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from config.settings import AppSettings, get_settings
from config.supplier_accounts import SupplierAccount
from settlement_automation.utils.files import (
    ensure_directory,
    get_file_size_bytes,
    sanitize_filename_part,
)
from settlement_automation.utils.hashing import calculate_sha256
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from config.settings import AppSettings, get_settings
from config.supplier_accounts import SupplierAccount
from settlement_automation.utils.files import ensure_directory, sanitize_filename_part


@dataclass(frozen=True)
class StoredRawReport:
    supplier_name: str
    portal_name: str
    business_date: date
    original_filename: str
    raw_path: Path
    file_hash: str
    size_bytes: int


    @property
    def hash_prefix(self) -> str:
        return self.file_hash[:12]


class DownloadManager:
    """
    Stores raw report files downloaded from supplier portals.

    This class does not parse reports.
    It only moves/copies files into the project's raw storage layout.
    """

    def __init__(self, settings: AppSettings | None = None):
        self.settings = settings or get_settings()

    def build_raw_report_dir(
            self,
            account: SupplierAccount,
            business_date: date,
    ) -> Path:
        """
        Store reports by supplier and month.

        New format:
            data/raw/{supplier}/YYYY/MM/
        """
        supplier = sanitize_filename_part(account.supplier_name)

        return (
                self.settings.raw_data_dir
                / supplier
                / f"{business_date.year:04d}"
                / f"{business_date.month:02d}"
        )



    def get_raw_directory(self, account: SupplierAccount, business_date: date) -> Path:
        year = f"{business_date.year:04d}"
        month = f"{business_date.month:02d}"
        day = f"{business_date.day:02d}"

        portal_name = sanitize_filename_part(account.portal_name)
        supplier_name = sanitize_filename_part(account.supplier_name)

        if portal_name == "dtn":
            return (
                self.settings.raw_data_dir
                / portal_name
                / supplier_name
                / year
                / month
                / day
            )

        return self.settings.raw_data_dir / supplier_name / year / month / day

    def build_raw_report_filename(
        self,
        account: SupplierAccount,
        business_date: date,
        source_path: Path,
    ) -> str:
        """
        New final raw filename format:
            {supplier}_{YYYY-MM-DD}.txt

        We intentionally do not include:
            - portal name
            - document name
            - row number
            - hash suffix
        """
        supplier = sanitize_filename_part(account.supplier_name)
        suffix = source_path.suffix or ".txt"

        return f"{supplier}_{business_date.isoformat()}{suffix}"

    def build_raw_report_path(
            self,
            account: SupplierAccount,
            business_date: date,
            source_path: Path,
    ) -> Path:
        raw_dir = self.build_raw_report_dir(
            account=account,
            business_date=business_date,
        )

        filename = self.build_raw_report_filename(
            account=account,
            business_date=business_date,
            source_path=source_path,
        )

        return raw_dir / filename

    def store_raw_report(
        self,
        source_path: Path,
        account: SupplierAccount,
        business_date: date,
        remove_source: bool = True,
    ) -> StoredRawReport:
        """
        Store one fetched raw report in the standardized raw folder.

        This intentionally overwrites the same supplier/date file on rerun.
        The hash is still calculated and returned for audit/logging, but it is
        no longer included in the filename.
        """
        source_path = Path(source_path)

        if not source_path.exists():
            raise FileNotFoundError(f"Source report does not exist: {source_path}")

        destination_path = self.build_raw_report_path(
            account=account,
            business_date=business_date,
            source_path=source_path,
        )

        ensure_directory(destination_path.parent)

        if remove_source:
            shutil.move(str(source_path), str(destination_path))
        else:
            shutil.copy2(str(source_path), str(destination_path))

        file_hash = calculate_sha256(destination_path)
        size_bytes = destination_path.stat().st_size

        return StoredRawReport(
            raw_path=destination_path,
            file_hash=file_hash,
            size_bytes=size_bytes,
        )