from datetime import date
from pathlib import Path

from config.dtn_reports import get_dtn_report_target
from config.settings import AppSettings, get_settings
from config.supplier_accounts import SupplierAccount
from settlement_automation.connectors.dtn_content_selection import (
    report_matches_required_content,
)
from settlement_automation.exceptions import SettlementAutomationError
from settlement_automation.utils.files import ensure_directory, sanitize_filename_part


class RawReportPreprocessingError(SettlementAutomationError):
    """Raised when a raw report cannot be prepared for parsing."""


def trim_text_to_first_marker(text: str, markers: tuple[str, ...]) -> str:
    if not text:
        return text

    for marker in markers:
        index = text.find(marker)

        if index >= 0:
            return text[index:].strip() + "\n"

    return text.strip() + "\n"


def prepare_raw_report_for_parser(
    raw_path: Path,
    account: SupplierAccount,
    business_date: date | None = None,
    settings: AppSettings | None = None,
) -> Path:
    """
    Prepare a raw report file for the existing supplier parser.

    For DTN reports, this removes portal chrome and verifies content markers.
    It does not mutate the original raw file.
    """
    settings = settings or get_settings()
    raw_path = Path(raw_path)

    if not raw_path.exists():
        raise FileNotFoundError(f"Raw report file does not exist: {raw_path}")

    if account.portal_name != "dtn":
        return raw_path

    target = get_dtn_report_target(account.supplier_name)

    raw_text = raw_path.read_text(encoding="utf-8", errors="replace")
    trimmed_text = trim_text_to_first_marker(
        text=raw_text,
        markers=target.content_start_markers,
    )

    if not report_matches_required_content(trimmed_text, target):
        raise RawReportPreprocessingError(
            f"DTN report content did not match expected markers for "
            f"supplier={account.supplier_name}. File={raw_path}"
        )

    supplier = sanitize_filename_part(account.supplier_name)
    date_part = business_date.isoformat() if business_date else "unknown_date"

    parser_input_dir = (
        settings.tmp_download_dir
        / "parser_input"
        / "dtn"
        / supplier
        / date_part
    )
    ensure_directory(parser_input_dir)

    parser_input_path = parser_input_dir / raw_path.name
    parser_input_path.write_text(trimmed_text, encoding="utf-8")

    return parser_input_path