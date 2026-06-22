from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from config.settings import get_settings
from config.supplier_accounts import get_supplier_account
from settlement_automation.connectors.download_manager import DownloadManager
from settlement_automation.utils.hashing import calculate_sha256


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


def test_store_sunoco_raw_report(tmp_path):
    settings = make_test_settings(tmp_path)
    manager = DownloadManager(settings=settings)

    account = get_supplier_account("sunoco")
    business_date = date(2026, 6, 18)

    source_file = tmp_path / "downloaded_sunoco.json"
    source_file.write_text('{"totalSalesAmount": 100.00}', encoding="utf-8")

    stored = manager.store_raw_report(
        source_path=source_file,
        account=account,
        business_date=business_date,
    )

    assert stored.supplier_name == "sunoco"
    assert stored.portal_name == "sunoco"
    assert stored.business_date == business_date
    assert stored.raw_path.exists()
    assert stored.raw_path.suffix == ".json"
    assert "sunoco_sunoco_2026-06-18" in stored.raw_path.name

    expected_dir = (
        settings.raw_data_dir
        / "sunoco"
        / "2026"
        / "06"
        / "18"
    )

    assert stored.raw_path.parent == expected_dir
    assert stored.file_hash == calculate_sha256(source_file)
    assert stored.size_bytes > 0


def test_store_citgo_dtn_raw_report(tmp_path):
    settings = make_test_settings(tmp_path)
    manager = DownloadManager(settings=settings)

    account = get_supplier_account("citgo")
    business_date = date(2026, 6, 18)

    source_file = tmp_path / "citgo report.txt"
    source_file.write_text("CITGO SAMPLE REPORT", encoding="utf-8")

    stored = manager.store_raw_report(
        source_path=source_file,
        account=account,
        business_date=business_date,
    )

    expected_dir = (
        settings.raw_data_dir
        / "dtn"
        / "citgo"
        / "2026"
        / "06"
        / "18"
    )

    assert stored.raw_path.exists()
    assert stored.raw_path.parent == expected_dir
    assert "citgo_dtn_2026-06-18" in stored.raw_path.name
    assert stored.raw_path.suffix == ".txt"


def test_store_valero_dtn_raw_report(tmp_path):
    settings = make_test_settings(tmp_path)
    manager = DownloadManager(settings=settings)

    account = get_supplier_account("valero")
    business_date = date(2026, 6, 18)

    source_file = tmp_path / "valero report.txt"
    source_file.write_text("VALERO SAMPLE REPORT", encoding="utf-8")

    stored = manager.store_raw_report(
        source_path=source_file,
        account=account,
        business_date=business_date,
    )

    expected_dir = (
        settings.raw_data_dir
        / "dtn"
        / "valero"
        / "2026"
        / "06"
        / "18"
    )

    assert stored.raw_path.exists()
    assert stored.raw_path.parent == expected_dir
    assert "valero_dtn_2026-06-18" in stored.raw_path.name


def test_store_raw_report_does_not_remove_source_by_default(tmp_path):
    settings = make_test_settings(tmp_path)
    manager = DownloadManager(settings=settings)

    account = get_supplier_account("citgo")
    business_date = date(2026, 6, 18)

    source_file = tmp_path / "report.txt"
    source_file.write_text("sample content", encoding="utf-8")

    stored = manager.store_raw_report(
        source_path=source_file,
        account=account,
        business_date=business_date,
    )

    assert source_file.exists()
    assert stored.raw_path.exists()
    assert source_file.read_text(encoding="utf-8") == stored.raw_path.read_text(
        encoding="utf-8"
    )


def test_store_raw_report_can_move_source_file(tmp_path):
    settings = make_test_settings(tmp_path)
    manager = DownloadManager(settings=settings)

    account = get_supplier_account("citgo")
    business_date = date(2026, 6, 18)

    source_file = tmp_path / "browser_download.txt"
    source_file.write_text("downloaded content", encoding="utf-8")

    stored = manager.store_raw_report(
        source_path=source_file,
        account=account,
        business_date=business_date,
        remove_source=True,
    )

    assert not source_file.exists()
    assert stored.raw_path.exists()
    assert stored.raw_path.read_text(encoding="utf-8") == "downloaded content"


def test_store_duplicate_same_file_returns_existing_path(tmp_path):
    settings = make_test_settings(tmp_path)
    manager = DownloadManager(settings=settings)

    account = get_supplier_account("sunoco")
    business_date = date(2026, 6, 18)

    source_file = tmp_path / "sunoco.json"
    source_file.write_text('{"same": true}', encoding="utf-8")

    first = manager.store_raw_report(
        source_path=source_file,
        account=account,
        business_date=business_date,
    )

    second = manager.store_raw_report(
        source_path=source_file,
        account=account,
        business_date=business_date,
    )

    assert first.raw_path == second.raw_path
    assert first.file_hash == second.file_hash


def test_store_missing_file_raises_error(tmp_path):
    settings = make_test_settings(tmp_path)
    manager = DownloadManager(settings=settings)

    account = get_supplier_account("citgo")
    missing_file = tmp_path / "missing.txt"

    with pytest.raises(FileNotFoundError):
        manager.store_raw_report(
            source_path=missing_file,
            account=account,
            business_date=date(2026, 6, 18),
        )