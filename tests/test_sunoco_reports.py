from config.sunoco_reports import get_sunoco_report_target


def test_sunoco_report_target():
    target = get_sunoco_report_target()

    assert target.supplier_name == "sunoco"
    assert target.report_format == "json"
    assert target.output_extension == ".txt"
    assert (
        target.portal_request_date_rule
        == "request_settlement_date_as_business_date_plus_one"
    )
    assert "SettlementSummary" in target.required_json_markers
    assert "totalSalesAmount" in target.required_json_markers
    assert "totalDealerFeeAmount" in target.required_json_markers
    assert "settlementDate" in target.required_json_markers
    assert "totalAdjustedNetAmount" in target.required_json_markers
    assert "shipToNumber" in target.required_json_markers