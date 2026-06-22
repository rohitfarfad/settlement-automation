import pytest

from config.dtn_reports import get_dtn_report_target


def test_citgo_dtn_report_target():
    target = get_dtn_report_target("citgo")

    assert target.supplier_name == "citgo"
    assert target.report_name == "Citgo Petroleum"
    assert target.report_group == "Credit Card"
    assert target.document_name == "Credit Card Memo"
    assert target.output_extension == ".txt"


def test_valero_dtn_report_target():
    target = get_dtn_report_target("valero")

    assert target.supplier_name == "valero"
    assert target.report_name == "Valero R & M"
    assert target.report_group == "Credit Card"
    assert target.document_name == "Credit Card Memo"
    assert target.output_extension == ".txt"


def test_unknown_dtn_supplier_raises_error():
    with pytest.raises(ValueError):
        get_dtn_report_target("sunoco")