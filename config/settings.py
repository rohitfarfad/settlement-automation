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

    notification_email_enabled: bool
    notification_email_mode: str
    notification_email_provider: str
    notification_output_dir: Path

    notification_email_to: str
    notification_email_cc: str
    notification_email_bcc: str
    notification_email_test_to: str

    graph_tenant_id: str
    graph_client_id: str
    graph_client_secret: str
    graph_sender_email: str


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
        headless_browser=_get_bool("HEADLESS_BROWSER", True),
        download_timeout_seconds=_get_int("DOWNLOAD_TIMEOUT_SECONDS", 60),
        max_retries=_get_int("MAX_RETRIES", 3),

        notification_email_enabled=_get_bool(
            "NOTIFICATION_EMAIL_ENABLED",
            False,
        ),
        notification_email_mode=os.getenv(
            "NOTIFICATION_EMAIL_MODE",
            "off",
        ).strip().lower(),
        notification_email_provider=os.getenv(
            "NOTIFICATION_EMAIL_PROVIDER",
            "graph",
        ).strip().lower(),
        notification_output_dir=output_dir / "notifications",

        notification_email_to=os.getenv("NOTIFICATION_EMAIL_TO", "").strip(),
        notification_email_cc=os.getenv("NOTIFICATION_EMAIL_CC", "").strip(),
        notification_email_bcc=os.getenv("NOTIFICATION_EMAIL_BCC", "").strip(),
        notification_email_test_to=os.getenv("NOTIFICATION_EMAIL_TEST_TO", "").strip(),

        graph_tenant_id=os.getenv("GRAPH_TENANT_ID", "").strip(),
        graph_client_id=os.getenv("GRAPH_CLIENT_ID", "").strip(),
        graph_client_secret=os.getenv("GRAPH_CLIENT_SECRET", "").strip(),
        graph_sender_email=os.getenv("GRAPH_SENDER_EMAIL", "").strip(),
    )