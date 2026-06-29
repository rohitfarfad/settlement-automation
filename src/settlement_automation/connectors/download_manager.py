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

    This class does not parse reports. It only moves/copies files into the
    project's raw storage layout.

    Current storage layout:
        data/raw/{supplier}/YYYY/MM/{supplier}_{YYYY-MM-DD}.txt
    """

    def __init__(self, settings: AppSettings | None = None):
        self.settings = settings or get_settings()

    def get_raw_directory(
        self,
        account: SupplierAccount,
        business_date: date,
    ) -> Path:
        supplier_name = sanitize_filename_part(account.supplier_name)

        return (
            self.settings.raw_data_dir
            / supplier_name
            / f"{business_date.year:04d}"
            / f"{business_date.month:02d}"
        )

    def build_raw_filename(
        self,
        source_path: Path,
        account: SupplierAccount,
        business_date: date,
        file_hash: str | None = None,
    ) -> str:
        """
        Final stored filename format:
            {supplier}_{YYYY-MM-DD}.txt

        file_hash is accepted for backward compatibility with older calls,
        but it is intentionally not used in the filename.
        """
        supplier_name = sanitize_filename_part(account.supplier_name)
        extension = Path(source_path).suffix.lower() or ".txt"

        return f"{supplier_name}_{business_date.isoformat()}{extension}"

    def store_raw_report(
        self,
        source_path: Path,
        account: SupplierAccount,
        business_date: date,
        remove_source: bool = False,
    ) -> StoredRawReport:
        """
        Store a downloaded report in data/raw.

        Same supplier + same business date now maps to the same final raw path.
        Reruns overwrite the existing file.
        """
        source_path = Path(source_path)

        if not source_path.exists():
            raise FileNotFoundError(f"Downloaded file does not exist: {source_path}")

        if not source_path.is_file():
            raise ValueError(f"Downloaded path is not a file: {source_path}")

        source_hash = calculate_sha256(source_path)
        source_size_bytes = get_file_size_bytes(source_path)

        raw_directory = self.get_raw_directory(
            account=account,
            business_date=business_date,
        )
        ensure_directory(raw_directory)

        raw_filename = self.build_raw_filename(
            source_path=source_path,
            account=account,
            business_date=business_date,
            file_hash=source_hash,
        )

        raw_path = raw_directory / raw_filename

        if raw_path.exists():
            raw_path.unlink()

        if remove_source:
            shutil.move(str(source_path), str(raw_path))
        else:
            shutil.copy2(source_path, raw_path)

        final_hash = calculate_sha256(raw_path)
        final_size_bytes = get_file_size_bytes(raw_path)

        return StoredRawReport(
            supplier_name=account.supplier_name,
            portal_name=account.portal_name,
            business_date=business_date,
            original_filename=source_path.name,
            raw_path=raw_path,
            file_hash=final_hash,
            size_bytes=final_size_bytes or source_size_bytes,
        )