from dataclasses import replace
from datetime import date

import pytest

from config.settings import get_settings
from config.supplier_accounts import get_supplier_account
from settlement_automation.connectors.download_manager import DownloadManager
from settlement_automation.connectors.mock_browser_portal import MockBrowserPortalConnector
from settlement_automation.ingestion.fetch_reports import fetch_reports_for_account


pytestmark = pytest.mark.browser


def make_test_settings(tmp_path):
    settings = get_settings()

    return replace(
        settings,
        data_dir=tmp_path / "data",
        raw_data_dir=tmp_path / "data" / "raw",
        tmp_download_dir=tmp_path / "data" / "tmp",
        output_dir=tmp_path / "output",
        log_dir=tmp_path / "output" / "logs",
        trace_dir=tmp_path / "output" / "traces",
    )


def test_mock_browser_download_to_raw_storage(tmp_path):
    settings = make_test_settings(tmp_path)
    manager = DownloadManager(settings=settings)
    account = get_supplier_account("citgo")

    def connector_factory(account):
        return MockBrowserPortalConnector(account=account, settings=settings)

    result = fetch_reports_for_account(
        account=account,
        business_date=date(2026, 6, 18),
        download_manager=manager,
        connector_factory=connector_factory,
        remove_downloaded_files=True,
    )

    assert result.succeeded
    assert len(result.stored_reports) == 1

    stored = result.stored_reports[0]

    assert stored.raw_path.exists()
    assert stored.raw_path.parent == (
        settings.raw_data_dir / "dtn" / "citgo" / "2026" / "06" / "18"
    )