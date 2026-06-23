from dataclasses import replace
from datetime import date

import pytest

from config.settings import get_settings
from config.supplier_accounts import get_supplier_account
from config.sunoco_reports import get_sunoco_report_target
from settlement_automation.connectors.sunoco_capture import (
    save_sunoco_json_text,
    validate_sunoco_json_text,
)
from settlement_automation.exceptions import PortalDownloadError


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


def test_validate_sunoco_json_text_accepts_valid_json():
    target = get_sunoco_report_target()

    json_text = """
    {
      "@odata.context": "https://api.portal.sunocolp.com/odata/$metadata#SettlementSummary",
      "@odata.count": 1,
      "value": [
        {
          "settlementDate": "2026-06-17T00:00:00",
          "totalSalesAmount": 10461.02,
          "totalDealerFeeAmount": -221.05,
          "totalAdjustedNetAmount": 10241.15,
          "location": {
            "shipToNumber": "0326461100"
          }
        }
      ]
    }
    """

    validate_sunoco_json_text(json_text, target)

def test_validate_sunoco_json_text_rejects_invalid_json():
    target = get_sunoco_report_target()

    with pytest.raises(PortalDownloadError):
        validate_sunoco_json_text("[object Object]", target)


def test_validate_sunoco_json_text_rejects_missing_markers():
    target = get_sunoco_report_target()

    json_text = """
    {
      "value": [
        {
          "settlementDate": "2026-06-17T00:00:00"
        }
      ]
    }
    """

    with pytest.raises(PortalDownloadError):
        validate_sunoco_json_text(json_text, target)


def test_save_sunoco_json_text_writes_tmp_json(tmp_path):
    settings = make_test_settings(tmp_path)
    account = get_supplier_account("sunoco")
    target = get_sunoco_report_target()

    json_text = """
        {
          "@odata.context": "https://api.portal.sunocolp.com/odata/$metadata#SettlementSummary",
          "@odata.count": 1,
          "value": [
            {
              "settlementDate": "2026-06-17T00:00:00",
              "totalSalesAmount": 10461.02,
              "totalDealerFeeAmount": -221.05,
              "totalAdjustedNetAmount": 10241.15,
              "location": {
                "shipToNumber": "0326461100"
              }
            }
          ]
        }
        """

    tmp_path_result = save_sunoco_json_text(
        json_text=json_text,
        settings=settings,
        account=account,
        business_date=date(2026, 6, 16),
        settlement_date=date(2026, 6, 17),
        target=target,
    )

    assert tmp_path_result.exists()
    assert tmp_path_result.suffix == ".txt"
    assert "sunoco_settlement_2026-06-17_business_2026-06-16" in tmp_path_result.name