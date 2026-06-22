from dataclasses import replace
from datetime import date
from pathlib import Path

from config.settings import get_settings
from config.supplier_accounts import get_supplier_account
from settlement_automation.connectors.base import SupplierPortalConnector
from settlement_automation.connectors.download_manager import DownloadManager
from settlement_automation.ingestion.fetch_reports import (
    fetch_reports_for_account,
    fetch_reports_for_suppliers,
)


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


class FakeSuccessfulConnector(SupplierPortalConnector):
    def __init__(self, account, source_files):
        super().__init__(account)
        self.source_files = source_files

    def fetch_reports(self, business_date: date) -> list[Path]:
        return self.source_files


class FakeFailingConnector(SupplierPortalConnector):
    def fetch_reports(self, business_date: date) -> list[Path]:
        raise RuntimeError("mock portal failure")


def test_fetch_reports_for_account_stores_downloaded_file(tmp_path):
    settings = make_test_settings(tmp_path)
    manager = DownloadManager(settings=settings)

    source_file = tmp_path / "citgo_download.txt"
    source_file.write_text("CITGO SAMPLE REPORT", encoding="utf-8")

    account = get_supplier_account("citgo")

    def connector_factory(account):
        return FakeSuccessfulConnector(account, [source_file])

    result = fetch_reports_for_account(
        account=account,
        business_date=date(2026, 6, 18),
        download_manager=manager,
        connector_factory=connector_factory,
        remove_downloaded_files=False,
    )

    assert result.succeeded
    assert result.supplier_name == "citgo"
    assert result.portal_name == "dtn"
    assert len(result.downloaded_files) == 1
    assert len(result.stored_reports) == 1

    stored = result.stored_reports[0]

    assert stored.raw_path.exists()
    assert stored.raw_path.parent == (
        settings.raw_data_dir / "dtn" / "citgo" / "2026" / "06" / "18"
    )
    assert "citgo_dtn_2026-06-18" in stored.raw_path.name


def test_fetch_reports_for_account_can_move_downloaded_file(tmp_path):
    settings = make_test_settings(tmp_path)
    manager = DownloadManager(settings=settings)

    source_file = tmp_path / "browser_download.txt"
    source_file.write_text("downloaded report", encoding="utf-8")

    account = get_supplier_account("valero")

    def connector_factory(account):
        return FakeSuccessfulConnector(account, [source_file])

    result = fetch_reports_for_account(
        account=account,
        business_date=date(2026, 6, 18),
        download_manager=manager,
        connector_factory=connector_factory,
        remove_downloaded_files=True,
    )

    assert result.succeeded
    assert not source_file.exists()
    assert result.stored_reports[0].raw_path.exists()


def test_fetch_reports_for_account_returns_failure_result(tmp_path):
    settings = make_test_settings(tmp_path)
    manager = DownloadManager(settings=settings)

    account = get_supplier_account("sunoco")

    def connector_factory(account):
        return FakeFailingConnector(account)

    result = fetch_reports_for_account(
        account=account,
        business_date=date(2026, 6, 18),
        download_manager=manager,
        connector_factory=connector_factory,
        remove_downloaded_files=False,
    )

    assert not result.succeeded
    assert result.status == "failed"
    assert result.supplier_name == "sunoco"
    assert "mock portal failure" in result.error_message
    assert result.stored_reports == []


def test_fetch_reports_for_suppliers_isolates_supplier_failures(tmp_path):
    settings = make_test_settings(tmp_path)
    manager = DownloadManager(settings=settings)

    citgo_source = tmp_path / "citgo.txt"
    citgo_source.write_text("CITGO SAMPLE REPORT", encoding="utf-8")

    def connector_factory(account):
        if account.supplier_name == "citgo":
            return FakeSuccessfulConnector(account, [citgo_source])

        return FakeFailingConnector(account)

    results = fetch_reports_for_suppliers(
        business_date=date(2026, 6, 18),
        supplier_names=["citgo", "sunoco"],
        download_manager=manager,
        connector_factory=connector_factory,
        remove_downloaded_files=False,
    )

    assert len(results) == 2

    citgo_result = next(result for result in results if result.supplier_name == "citgo")
    sunoco_result = next(result for result in results if result.supplier_name == "sunoco")

    assert citgo_result.succeeded
    assert not sunoco_result.succeeded
    assert "mock portal failure" in sunoco_result.error_message