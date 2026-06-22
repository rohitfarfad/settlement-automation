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

    This class does not parse reports.
    It only moves/copies files into the project's raw storage layout.
    """

    def __init__(self, settings: AppSettings | None = None):
        self.settings = settings or get_settings()

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

    def build_raw_filename(
        self,
        source_path: Path,
        account: SupplierAccount,
        business_date: date,
        file_hash: str,
    ) -> str:
        source_path = Path(source_path)

        supplier_name = sanitize_filename_part(account.supplier_name)
        portal_name = sanitize_filename_part(account.portal_name)
        original_stem = sanitize_filename_part(source_path.stem)
        extension = source_path.suffix.lower() or ".dat"
        hash_prefix = file_hash[:12]

        return (
            f"{supplier_name}_{portal_name}_"
            f"{business_date.isoformat()}_"
            f"{original_stem}_"
            f"{hash_prefix}"
            f"{extension}"
        )

    def store_raw_report(
        self,
        source_path: Path,
        account: SupplierAccount,
        business_date: date,
        remove_source: bool = False,
    ) -> StoredRawReport:
        """
        Store a downloaded report in data/raw.

        By default this copies the file so tests/manual files are not destroyed.
        For real browser tmp downloads, pass remove_source=True to move the file.
        """
        source_path = Path(source_path)

        if not source_path.exists():
            raise FileNotFoundError(f"Downloaded file does not exist: {source_path}")

        if not source_path.is_file():
            raise ValueError(f"Downloaded path is not a file: {source_path}")

        file_hash = calculate_sha256(source_path)
        size_bytes = get_file_size_bytes(source_path)

        raw_directory = self.get_raw_directory(account, business_date)
        ensure_directory(raw_directory)

        raw_filename = self.build_raw_filename(
            source_path=source_path,
            account=account,
            business_date=business_date,
            file_hash=file_hash,
        )

        raw_path = raw_directory / raw_filename

        if raw_path.exists():
            existing_hash = calculate_sha256(raw_path)

            if existing_hash == file_hash:
                if remove_source and source_path.resolve() != raw_path.resolve():
                    source_path.unlink()

                return StoredRawReport(
                    supplier_name=account.supplier_name,
                    portal_name=account.portal_name,
                    business_date=business_date,
                    original_filename=source_path.name,
                    raw_path=raw_path,
                    file_hash=file_hash,
                    size_bytes=size_bytes,
                )

            raise FileExistsError(
                f"Raw report path already exists with different content: {raw_path}"
            )

        if remove_source:
            shutil.move(str(source_path), str(raw_path))
        else:
            shutil.copy2(source_path, raw_path)

        return StoredRawReport(
            supplier_name=account.supplier_name,
            portal_name=account.portal_name,
            business_date=business_date,
            original_filename=source_path.name,
            raw_path=raw_path,
            file_hash=file_hash,
            size_bytes=size_bytes,
        )