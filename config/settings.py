import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _get_bool(env_name: str, default: bool) -> bool:
    value = os.getenv(env_name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_int(env_name: str, default: int) -> int:
    value = os.getenv(env_name)
    if value is None or value.strip() == "":
        return default

    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{env_name} must be an integer. Got: {value}") from exc


def _get_path(env_name: str, default: Path) -> Path:
    value = os.getenv(env_name)
    if value is None or value.strip() == "":
        return default
    return Path(value).expanduser().resolve()


@dataclass(frozen=True)
class AppSettings:
    project_root: Path
    data_dir: Path
    raw_data_dir: Path
    tmp_download_dir: Path
    output_dir: Path
    log_dir: Path
    trace_dir: Path

    excel_workbook_root: Path
    excel_output_dir: Path
    excel_audit_dir: Path

    headless_browser: bool
    download_timeout_seconds: int
    max_retries: int


def get_settings() -> AppSettings:
    output_dir = PROJECT_ROOT / "output"

    return AppSettings(
        project_root=PROJECT_ROOT,
        data_dir=PROJECT_ROOT / "data",
        raw_data_dir=PROJECT_ROOT / "data" / "raw",
        tmp_download_dir=PROJECT_ROOT / "data" / "tmp",
        output_dir=output_dir,
        log_dir=output_dir / "logs",
        trace_dir=output_dir / "traces",
        excel_workbook_root=_get_path(
            "EXCEL_WORKBOOK_ROOT",
            PROJECT_ROOT / "data" / "workbooks",
        ),
        excel_output_dir=_get_path(
            "EXCEL_OUTPUT_DIR",
            output_dir / "excel",
        ),
        excel_audit_dir=_get_path(
            "EXCEL_AUDIT_DIR",
            output_dir / "excel_audit",
        ),
        headless_browser=_get_bool("HEADLESS_BROWSER", True),
        download_timeout_seconds=_get_int("DOWNLOAD_TIMEOUT_SECONDS", 60),
        max_retries=_get_int("MAX_RETRIES", 3),
    )