from config.sunoco_reports import get_sunoco_report_target


def test_sunoco_report_target():
    target = get_sunoco_report_target()

    assert target.supplier_name == "sunoco"
    assert target.report_format == "json"
    assert target.output_extension == ".json"
    assert target.business_date_rule == "settlement_date_minus_one_day"
    assert "totalSalesAmount" in target.required_json_markers
    assert "totalDealerFeeAmount" in target.required_json_markers
    assert "settlementDate" in target.required_json_markers