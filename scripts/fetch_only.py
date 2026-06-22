from _path_setup import PROJECT_ROOT  # noqa: F401

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

from config.settings import get_settings
from config.supplier_accounts import get_supplier_account
from settlement_automation.connectors import get_connector
from settlement_automation.connectors.base import SupplierPortalConnector
from settlement_automation.connectors.download_manager import DownloadManager
from settlement_automation.ingestion.fetch_reports import fetch_reports_for_account
from settlement_automation.utils.env import load_local_env

class LocalFileMockConnector(SupplierPortalConnector):
    """
    Test/dev connector that pretends a local file was downloaded from a portal.

    This allows us to test the fetching pipeline without logging into real supplier websites.
    """

    def __init__(self, account, source_file: Path):
        super().__init__(account)
        self.source_file = Path(source_file)

    def fetch_reports(self, business_date: date) -> list[Path]:
        if not self.source_file.exists():
            raise FileNotFoundError(f"Mock source file not found: {self.source_file}")

        if not self.source_file.is_file():
            raise ValueError(f"Mock source path is not a file: {self.source_file}")

        return [self.source_file]


def parse_business_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid date: {value}. Expected format: YYYY-MM-DD"
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch supplier reports and store raw files only. No parsing or Excel output."
    )

    parser.add_argument(
        "--supplier",
        required=True,
        help="Supplier name to fetch. Example: sunoco, citgo, valero",
    )

    parser.add_argument(
        "--business-date",
        type=parse_business_date,
        default=date.today() - timedelta(days=1),
        help="Business date to fetch in YYYY-MM-DD format. Defaults to yesterday.",
    )

    parser.add_argument(
        "--mock-source-file",
        type=Path,
        default=None,
        help="Local file to use as a fake downloaded portal report for testing.",
    )

    parser.add_argument(
        "--remove-source",
        action="store_true",
        help="Move the source file instead of copying it. Do not use with sample files.",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    settings = get_settings()
    load_local_env(settings.project_root)

    account = get_supplier_account(args.supplier)
    manager = DownloadManager(settings=settings)

    if args.mock_source_file:
        connector_factory = lambda account: LocalFileMockConnector(
            account=account,
            source_file=args.mock_source_file,
        )
        remove_downloaded_files = args.remove_source
    else:
        connector_factory = None
        remove_downloaded_files = True

    result = fetch_reports_for_account(
        account=account,
        business_date=args.business_date,
        download_manager=manager,
        connector_factory=connector_factory if connector_factory is not None else get_connector,
        remove_downloaded_files=remove_downloaded_files,
        raise_on_error=False,
    )

    if not result.succeeded:
        print(
            f"[FAILED] supplier={result.supplier_name} "
            f"portal={result.portal_name} "
            f"business_date={result.business_date} "
            f"error={result.error_message}",
            file=sys.stderr,
        )
        return 1

    print(
        f"[SUCCESS] supplier={result.supplier_name} "
        f"portal={result.portal_name} "
        f"business_date={result.business_date}"
    )

    for stored_report in result.stored_reports:
        print(f"  raw_path={stored_report.raw_path}")
        print(f"  hash={stored_report.file_hash}")
        print(f"  size_bytes={stored_report.size_bytes}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())