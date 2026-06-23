import pytest

from settlement_automation.ingestion.supplier_selection import (
    group_suppliers_by_portal,
    parse_supplier_selection,
)


def test_parse_single_supplier():
    assert parse_supplier_selection("citgo") == ["citgo"]


def test_parse_multiple_suppliers():
    assert parse_supplier_selection("citgo,valero") == ["citgo", "valero"]


def test_parse_dtn_shortcut():
    assert parse_supplier_selection("dtn") == ["citgo", "valero"]


def test_parse_all_shortcut():
    assert parse_supplier_selection("all") == ["citgo", "valero", "sunoco"]


def test_parse_removes_duplicates():
    assert parse_supplier_selection("citgo,citgo,valero") == ["citgo", "valero"]


def test_parse_rejects_unknown_supplier():
    with pytest.raises(ValueError):
        parse_supplier_selection("shell")


def test_group_suppliers_by_portal_for_dtn_only():
    groups = group_suppliers_by_portal(["citgo", "valero"])

    assert len(groups) == 1
    assert groups[0].portal_name == "dtn"
    assert groups[0].supplier_names == ["citgo", "valero"]


def test_group_suppliers_by_portal_for_all_suppliers():
    groups = group_suppliers_by_portal(["citgo", "valero", "sunoco"])

    assert len(groups) == 2

    assert groups[0].portal_name == "dtn"
    assert groups[0].supplier_names == ["citgo", "valero"]

    assert groups[1].portal_name == "sunoco"
    assert groups[1].supplier_names == ["sunoco"]