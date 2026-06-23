from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse

from config.dtn_reports import DTNReportTarget
from config.settings import AppSettings
from config.supplier_accounts import SupplierAccount
from settlement_automation.exceptions import PortalDownloadError
from settlement_automation.utils.files import ensure_directory, sanitize_filename_part


@dataclass(frozen=True)
class CapturedDTNReport:
    supplier_name: str
    business_date: date
    row_index: int
    source_url: str
    tmp_path: Path
    size_bytes: int


from datetime import date
from pathlib import Path

from config.dtn_reports import DTNReportTarget
from config.settings import AppSettings
from config.supplier_accounts import SupplierAccount
from settlement_automation.exceptions import PortalDownloadError
from settlement_automation.utils.files import ensure_directory, sanitize_filename_part


def build_dtn_visible_report_path(
    settings: AppSettings,
    account: SupplierAccount,
    target: DTNReportTarget,
    business_date: date,
    row_index: int,
) -> Path:
    supplier = sanitize_filename_part(account.supplier_name)
    document = sanitize_filename_part(target.document_name)
    date_text = business_date.isoformat()

    tmp_dir = settings.tmp_download_dir / "dtn" / supplier / date_text
    ensure_directory(tmp_dir)

    return tmp_dir / f"{supplier}_{document}_{date_text}_row_{row_index}.txt"


def click_matching_report_row(row) -> None:
    """
    DTN opens report content through JavaScript click behavior.
    There is no normal download link.
    """
    candidates = []

    try:
        cells = row.locator("td")
        cell_count = cells.count()

        if cell_count > 0:
            candidates.append(cells.nth(0))  # Supplier cell

        if cell_count > 3:
            candidates.append(cells.nth(3))  # Document cell

    except Exception:
        pass

    candidates.append(row)

    last_error = None

    for candidate in candidates:
        try:
            candidate.click(force=True, timeout=10000)
            return
        except Exception as exc:
            last_error = exc

    raise PortalDownloadError(f"Could not click DTN report row. Last error: {last_error}")


def get_best_visible_report_text(page) -> str:
    """
    Capture the visible raw report text after DTN opens the report.
    """
    selectors = [
        "pre",
        "textarea",
        "[id*='message' i]",
        "[id*='report' i]",
        "[class*='message' i]",
        "[class*='report' i]",
        "body",
    ]

    best_text = ""

    for selector in selectors:
        locator = page.locator(selector)

        try:
            count = locator.count()
        except Exception:
            continue

        for index in range(count):
            item = locator.nth(index)

            try:
                if not item.is_visible():
                    continue
            except Exception:
                pass

            try:
                text = item.inner_text(timeout=5000)
            except Exception:
                continue

            text = text.strip()

            if len(text) > len(best_text):
                best_text = text

    return best_text


def trim_dtn_report_text(
    visible_text: str,
    target: DTNReportTarget,
) -> str:
    """
    Remove DTN portal chrome before the actual report body.
    """
    if not visible_text:
        return visible_text

    for marker in target.content_start_markers:
        index = visible_text.find(marker)

        if index >= 0:
            return visible_text[index:].strip() + "\n"

    return visible_text.strip() + "\n"


def capture_visible_dtn_report_text_from_row(
    page,
    row,
    target: DTNReportTarget,
) -> str:
    click_matching_report_row(row)

    # DTN opens the report in the same page.
    page.wait_for_timeout(5000)

    visible_text = get_best_visible_report_text(page)
    return trim_dtn_report_text(visible_text, target)


def save_dtn_report_text(
    report_text: str,
    settings: AppSettings,
    account: SupplierAccount,
    target: DTNReportTarget,
    business_date: date,
    row_index: int,
) -> Path:
    if not report_text.strip():
        raise PortalDownloadError(
            f"Cannot save empty DTN report text for supplier={account.supplier_name}"
        )

    tmp_path = build_dtn_visible_report_path(
        settings=settings,
        account=account,
        target=target,
        business_date=business_date,
        row_index=row_index,
    )

    tmp_path.write_text(report_text, encoding="utf-8")

    return tmp_path