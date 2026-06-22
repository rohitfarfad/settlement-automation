from dataclasses import dataclass


@dataclass(frozen=True)
class DTNReportTarget:
    supplier_name: str
    report_name: str
    report_group: str
    document_name: str
    output_extension: str = ".txt"

    # We may see multiple rows with same Supplier/Group/Document.
    # The actual report should be selected by content, not file size.
    required_content_markers: tuple[str, ...] = ()
    rejected_content_markers: tuple[str, ...] = ()
    content_start_markers: tuple[str, ...] = ()


DTN_REPORT_TARGETS = {
    "citgo": DTNReportTarget(
        supplier_name="citgo",
        report_name="Citgo Petroleum",
        report_group="Credit Card",
        document_name="Credit Card Memo",
        output_extension=".txt",
        required_content_markers=(
            "CITGO DAILY RECEIVED TRANSACTION SUMMARY",
        ),
        rejected_content_markers=(
            "PREPAID CARD ACTIVATIONS",
        ),
        content_start_markers=(
            "CITGO PETROLEUM",
            "K4SY",
        ),
    ),
    "valero": DTNReportTarget(
        supplier_name="valero",
        report_name="Valero R & M",
        report_group="Credit Card",
        document_name="Credit Card Memo",
        output_extension=".txt",
        # Keep this broad for now until we inspect the exact Valero header.
        # If Valero has multiple Credit Card Memo rows later, add a stricter marker here.
        required_content_markers=(),
        rejected_content_markers=(),
        content_start_markers=(
            "VALERO",
            "VALERO R & M",
        ),
    ),
}


def get_dtn_report_target(supplier_name: str) -> DTNReportTarget:
    supplier_key = supplier_name.lower()

    try:
        return DTN_REPORT_TARGETS[supplier_key]
    except KeyError as exc:
        raise ValueError(f"No DTN report target configured for supplier={supplier_name}") from exc