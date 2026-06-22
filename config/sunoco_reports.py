from dataclasses import dataclass


@dataclass(frozen=True)
class SunocoReportTarget:
    supplier_name: str
    report_format: str
    output_extension: str
    portal_request_date_rule: str
    required_json_markers: tuple[str, ...]


SUNOCO_REPORT_TARGET = SunocoReportTarget(
    supplier_name="sunoco",
    report_format="json",
    output_extension=".json",
    portal_request_date_rule="request_settlement_date_as_business_date_plus_one",
    required_json_markers=(
        "totalSalesAmount",
        "totalDealerFeeAmount",
        "settlementDate",
    ),
)


def get_sunoco_report_target() -> SunocoReportTarget:
    return SUNOCO_REPORT_TARGET