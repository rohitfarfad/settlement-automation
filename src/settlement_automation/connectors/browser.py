from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from config.settings import AppSettings, get_settings
from config.supplier_accounts import SupplierAccount
from settlement_automation.exceptions import BrowserAutomationError
from settlement_automation.utils.files import ensure_directory, sanitize_filename_part


@dataclass
class BrowserSession:
    page: object
    context: object
    browser: object
    playwright: object
    download_dir: Path


def _load_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserAutomationError(
            "Playwright is not installed. Run: pip install playwright"
        ) from exc

    return sync_playwright


def _build_session_download_dir(
    settings: AppSettings,
    account: SupplierAccount,
) -> Path:
    portal_name = sanitize_filename_part(account.portal_name)
    supplier_name = sanitize_filename_part(account.supplier_name)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:8]

    return settings.tmp_download_dir / portal_name / supplier_name / run_id


def _build_artifact_prefix(account: SupplierAccount) -> str:
    portal_name = sanitize_filename_part(account.portal_name)
    supplier_name = sanitize_filename_part(account.supplier_name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    return f"{portal_name}_{supplier_name}_{timestamp}"


def capture_failure_artifacts(
    page: object,
    settings: AppSettings,
    account: SupplierAccount,
    step_name: str,
) -> dict[str, Path]:
    """
    Capture screenshot and HTML when browser automation fails.

    These files help debug supplier portal layout/login/download failures.
    """
    ensure_directory(settings.trace_dir)

    artifact_prefix = _build_artifact_prefix(account)
    step = sanitize_filename_part(step_name)

    screenshot_path = settings.trace_dir / f"{artifact_prefix}_{step}.png"
    html_path = settings.trace_dir / f"{artifact_prefix}_{step}.html"

    artifacts = {}

    try:
        page.screenshot(path=str(screenshot_path), full_page=True)
        artifacts["screenshot"] = screenshot_path
    except Exception:
        pass

    try:
        html_path.write_text(page.content(), encoding="utf-8")
        artifacts["html"] = html_path
    except Exception:
        pass

    return artifacts


@contextmanager
def open_browser_session(
    account: SupplierAccount,
    settings: AppSettings | None = None,
    record_trace: bool = True,
) -> Iterator[BrowserSession]:
    """
    Open an isolated Playwright browser session for one supplier account.

    Each supplier account gets a fresh context, so CITGO and Valero DTN sessions
    cannot leak cookies/session state into each other.
    """
    settings = settings or get_settings()
    sync_playwright = _load_playwright()

    download_dir = _build_session_download_dir(settings, account)
    ensure_directory(download_dir)
    ensure_directory(settings.trace_dir)

    playwright_context_manager = sync_playwright()
    playwright = playwright_context_manager.start()

    browser = None
    context = None

    try:
        browser = playwright.chromium.launch(
            headless=settings.headless_browser,
        )

        context = browser.new_context(
            accept_downloads=True,
        )

        if record_trace:
            context.tracing.start(
                screenshots=True,
                snapshots=True,
                sources=True,
            )

        page = context.new_page()

        yield BrowserSession(
            page=page,
            context=context,
            browser=browser,
            playwright=playwright,
            download_dir=download_dir,
        )

        if record_trace:
            context.tracing.stop()

    except Exception as exc:
        if context is not None and record_trace:
            trace_path = settings.trace_dir / f"{_build_artifact_prefix(account)}_trace.zip"
            try:
                context.tracing.stop(path=str(trace_path))
            except Exception:
                pass

        raise BrowserAutomationError(
            f"Browser automation failed for supplier={account.supplier_name}, "
            f"portal={account.portal_name}: {exc}"
        ) from exc

    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass

        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass

        try:
            playwright_context_manager.stop()
        except Exception:
            pass