import json
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from config.settings import AppSettings, get_settings
from config.supplier_accounts import SupplierAccount
from settlement_automation.utils.files import ensure_directory, sanitize_filename_part


@dataclass
class DiagnosticRecord:
    supplier_name: str
    portal_name: str
    business_date: str
    step_name: str
    status: str
    message: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    page_url: str | None = None
    page_title: str | None = None
    screenshot_path: str | None = None
    html_path: str | None = None
    trace_path: str | None = None
    traceback_text: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def build_diagnostic_dir(
    settings: AppSettings,
    account: SupplierAccount,
    business_date,
) -> Path:
    supplier = sanitize_filename_part(account.supplier_name)
    date_text = str(business_date)

    output_dir = settings.output_dir / "diagnostics" / supplier / date_text
    ensure_directory(output_dir)

    return output_dir


def write_diagnostic_record(
    record: DiagnosticRecord,
    settings: AppSettings | None = None,
) -> Path:
    settings = settings or get_settings()

    supplier = sanitize_filename_part(record.supplier_name)
    date_text = sanitize_filename_part(record.business_date)
    step = sanitize_filename_part(record.step_name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    output_dir = settings.output_dir / "diagnostics" / supplier / date_text
    ensure_directory(output_dir)

    output_path = output_dir / f"{timestamp}_{step}.json"

    output_path.write_text(
        json.dumps(asdict(record), indent=2, default=str),
        encoding="utf-8",
    )

    return output_path


def capture_page_state(page) -> tuple[str | None, str | None]:
    try:
        page_url = page.url
    except Exception:
        page_url = None

    try:
        page_title = page.title()
    except Exception:
        page_title = None

    return page_url, page_title


def write_exception_diagnostic(
    *,
    account: SupplierAccount,
    business_date,
    step_name: str,
    exc: Exception,
    settings: AppSettings | None = None,
    page=None,
    artifact_paths: dict[str, Path] | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    settings = settings or get_settings()

    page_url = None
    page_title = None

    if page is not None:
        page_url, page_title = capture_page_state(page)

    artifact_paths = artifact_paths or {}

    record = DiagnosticRecord(
        supplier_name=account.supplier_name,
        portal_name=account.portal_name,
        business_date=str(business_date),
        step_name=step_name,
        status="failed",
        message=str(exc),
        page_url=page_url,
        page_title=page_title,
        screenshot_path=str(artifact_paths.get("screenshot")) if artifact_paths.get("screenshot") else None,
        html_path=str(artifact_paths.get("html")) if artifact_paths.get("html") else None,
        trace_path=str(artifact_paths.get("trace")) if artifact_paths.get("trace") else None,
        traceback_text=traceback.format_exc(),
        extra=extra or {},
    )

    return write_diagnostic_record(record, settings=settings)