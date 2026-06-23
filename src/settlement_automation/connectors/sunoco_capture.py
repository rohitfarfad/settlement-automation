import json
from datetime import date
from pathlib import Path
from typing import Any

from config.settings import AppSettings
from config.supplier_accounts import SupplierAccount
from config.sunoco_reports import SunocoReportTarget
from settlement_automation.exceptions import PortalDownloadError
from settlement_automation.utils.files import ensure_directory, sanitize_filename_part


def build_sunoco_tmp_report_path(
    settings: AppSettings,
    account: SupplierAccount,
    business_date: date,
    settlement_date: date,
    target: SunocoReportTarget,
) -> Path:
    supplier = sanitize_filename_part(account.supplier_name)

    tmp_dir = settings.tmp_download_dir / "sunoco" / business_date.isoformat()
    ensure_directory(tmp_dir)

    return tmp_dir / (
        f"{supplier}_settlement_{settlement_date.isoformat()}_"
        f"business_{business_date.isoformat()}{target.output_extension}"
    )

def validate_sunoco_json_text(
    json_text: str,
    target: SunocoReportTarget,
) -> None:
    if not json_text or not json_text.strip():
        raise PortalDownloadError("Sunoco JSON response was empty.")

    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise PortalDownloadError("Sunoco response is not valid JSON.") from exc

    serialized = json.dumps(parsed)

    missing_markers = [
        marker
        for marker in target.required_json_markers
        if marker not in serialized
    ]

    if missing_markers:
        raise PortalDownloadError(
            f"Sunoco JSON response is missing expected markers: {missing_markers}"
        )


def save_sunoco_json_text(
    json_text: str,
    settings: AppSettings,
    account: SupplierAccount,
    business_date: date,
    settlement_date: date,
    target: SunocoReportTarget,
) -> Path:
    validate_sunoco_json_text(json_text, target)

    tmp_path = build_sunoco_tmp_report_path(
        settings=settings,
        account=account,
        business_date=business_date,
        settlement_date=settlement_date,
        target=target,
    )

    # Reformat JSON for stable readable raw storage.
    parsed: Any = json.loads(json_text)
    tmp_path.write_text(
        json.dumps(parsed, indent=4),
        encoding="utf-8",
    )

    return tmp_path