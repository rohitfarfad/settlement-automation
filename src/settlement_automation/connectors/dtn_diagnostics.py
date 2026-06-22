from config.dtn_reports import DTNReportTarget


def summarize_dtn_rows(page, max_rows: int = 50) -> list[str]:
    rows = page.locator("tr")
    output = []

    try:
        count = min(rows.count(), max_rows)
    except Exception:
        return output

    for index in range(count):
        try:
            text = " ".join(rows.nth(index).inner_text(timeout=2000).split())
        except Exception:
            continue

        if text:
            output.append(text)

    return output


def summarize_matching_rows(page, target: DTNReportTarget) -> list[str]:
    from settlement_automation.connectors.dtn_page import find_matching_report_rows_by_text

    rows = find_matching_report_rows_by_text(page, target)
    output = []

    for row in rows:
        try:
            text = " ".join(row.inner_text(timeout=3000).split())
        except Exception:
            continue

        if text:
            output.append(text)

    return output