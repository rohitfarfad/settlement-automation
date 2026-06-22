from config.dtn_reports import DTNReportTarget


def normalize_report_text(text: str) -> str:
    return " ".join(text.upper().split())


def report_matches_required_content(
    report_text: str,
    target: DTNReportTarget,
) -> bool:
    """
    Decide whether a captured DTN report is the intended report.

    For CITGO, this accepts the daily transaction summary and rejects
    prepaid activations even though both appear as Credit Card Memo rows.
    """
    normalized = normalize_report_text(report_text)

    for marker in target.rejected_content_markers:
        if marker.upper() in normalized:
            return False

    for marker in target.required_content_markers:
        if marker.upper() not in normalized:
            return False

    return True