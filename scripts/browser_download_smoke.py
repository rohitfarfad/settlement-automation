from _path_setup import PROJECT_ROOT  # noqa: F401

import argparse
from datetime import date, timedelta

from config.settings import get_settings
from config.supplier_accounts import get_supplier_account
from settlement_automation.connectors.download_manager import DownloadManager
from settlement_automation.connectors.mock_browser_portal import MockBrowserPortalConnector
from settlement_automation.ingestion.fetch_reports import fetch_reports_for_account
from settlement_automation.utils.env import load_local_env


def parse_business_date(value: str) -> date:
    return date.fromisoformat(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Smoke test Playwright browser download and raw storage."
    )

    parser.add_argument(
        "--supplier",
        required=True,
        choices=["sunoco", "citgo", "valero"],
    )

    parser.add_argument(
        "--business-date",
        type=parse_business_date,
        default=date.today() - timedelta(days=1),
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    settings = get_settings()
    load_local_env(settings.project_root)

    account = get_supplier_account(args.supplier)
    manager = DownloadManager(settings=settings)

    def connector_factory(account):
        return MockBrowserPortalConnector(account=account, settings=settings)

    result = fetch_reports_for_account(
        account=account,
        business_date=args.business_date,
        download_manager=manager,
        connector_factory=connector_factory,
        remove_downloaded_files=True,
        raise_on_error=False,
    )

    if not result.succeeded:
        print(
            f"[FAILED] supplier={result.supplier_name} "
            f"portal={result.portal_name} "
            f"error={result.error_message}"
        )
        return 1

    print(
        f"[SUCCESS] browser smoke test completed for "
        f"supplier={result.supplier_name}, portal={result.portal_name}, "
        f"business_date={result.business_date}"
    )

    for stored_report in result.stored_reports:
        print(f"  raw_path={stored_report.raw_path}")
        print(f"  hash={stored_report.file_hash}")
        print(f"  size_bytes={stored_report.size_bytes}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())