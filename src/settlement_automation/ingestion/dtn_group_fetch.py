from datetime import date
from pathlib import Path

from config.dtn_reports import get_dtn_report_target
from config.portal_rules import get_dtn_portal_rule
from config.settings import AppSettings, get_settings
from config.supplier_accounts import SupplierAccount, get_supplier_account
from settlement_automation.connectors.browser import (
    capture_failure_artifacts,
    open_browser_session,
)
from settlement_automation.connectors.credentials import load_credentials
from settlement_automation.connectors.download_manager import (
    DownloadManager,
    StoredRawReport,
)
from settlement_automation.connectors.dtn_capture import (
    capture_visible_dtn_report_text_from_row,
    save_dtn_report_text,
)
from settlement_automation.connectors.dtn_content_selection import (
    report_matches_required_content,
)
from settlement_automation.connectors.dtn_diagnostics import (
    summarize_dtn_rows,
    summarize_matching_rows,
)
from settlement_automation.connectors.dtn_page import (
    find_matching_report_rows_by_text,
    login_to_dtn,
    open_dataconnect_direct,
    select_dataconnect_date,
    wait_for_dataconnect_message_list_loaded,
)
from settlement_automation.exceptions import PortalDownloadError
from settlement_automation.ingestion.fetch_reports import FetchResult
from settlement_automation.services.diagnostics import write_exception_diagnostic


def capture_one_dtn_supplier_report_from_open_session(
    *,
    page,
    account: SupplierAccount,
    business_date: date,
    settings: AppSettings,
) -> list[Path]:
    """
    Capture one supplier's DTN report using an already-authenticated DTN session.

    This function does not login. Caller owns the browser session.

    Important:
    We wait only for the message list to load, not for the specific target row.
    This makes missing reports fail fast, which is important for date ranges
    where weekends may not have CITGO/Valero reports.
    """
    portal_rule = get_dtn_portal_rule()
    target = get_dtn_report_target(account.supplier_name)

    open_dataconnect_direct(
        page=page,
        dataconnect_url=portal_rule.dataconnect_url,
    )

    select_dataconnect_date(
        page=page,
        business_date=business_date,
    )

    wait_for_dataconnect_message_list_loaded(
        page=page,
        timeout_seconds=15,
    )

    rows = find_matching_report_rows_by_text(page, target)

    if not rows:
        raise PortalDownloadError(
            f"No DTN rows found for supplier={account.supplier_name}, "
            f"business_date={business_date}"
        )

    last_captured_preview = ""

    for row_index in range(1, len(rows) + 1):
        # Clicking a report opens it in the same page, so reopen DataConnect
        # before each candidate row attempt.
        open_dataconnect_direct(
            page=page,
            dataconnect_url=portal_rule.dataconnect_url,
        )

        select_dataconnect_date(
            page=page,
            business_date=business_date,
        )

        wait_for_dataconnect_message_list_loaded(
            page=page,
            timeout_seconds=15,
        )

        fresh_rows = find_matching_report_rows_by_text(page, target)

        if row_index > len(fresh_rows):
            continue

        row = fresh_rows[row_index - 1]

        report_text = capture_visible_dtn_report_text_from_row(
            page=page,
            row=row,
            target=target,
        )

        last_captured_preview = report_text[:300]

        if not report_matches_required_content(report_text, target):
            continue

        tmp_path = save_dtn_report_text(
            report_text=report_text,
            settings=settings,
            account=account,
            target=target,
            business_date=business_date,
            row_index=row_index,
        )

        return [tmp_path]

    raise PortalDownloadError(
        f"No DTN report content matched required markers for "
        f"supplier={account.supplier_name}, business_date={business_date}. "
        f"Last captured preview: {last_captured_preview!r}"
    )

def make_failed_fetch_result(
    *,
    account: SupplierAccount,
    business_date: date,
    error_message: str,
) -> FetchResult:
    return FetchResult(
        supplier_name=account.supplier_name,
        portal_name=account.portal_name,
        business_date=business_date,
        status="failed",
        downloaded_files=[],
        stored_reports=[],
        error_message=error_message,
    )


def make_success_fetch_result(
    *,
    account: SupplierAccount,
    business_date: date,
    downloaded_files: list[Path],
    stored_reports: list[StoredRawReport],
) -> FetchResult:
    return FetchResult(
        supplier_name=account.supplier_name,
        portal_name=account.portal_name,
        business_date=business_date,
        status="success",
        downloaded_files=downloaded_files,
        stored_reports=stored_reports,
    )


def fetch_dtn_reports_for_supplier_group(
    *,
    supplier_names: list[str],
    business_date: date,
    download_manager: DownloadManager,
    settings: AppSettings | None = None,
    remove_downloaded_files: bool = True,
) -> dict[str, FetchResult]:
    """
    Fetch multiple DTN supplier reports in one browser login/session.

    Intended for:
        citgo + valero

    Returns one FetchResult per supplier, matching the existing fetch contract.
    """
    settings = settings or get_settings()
    portal_rule = get_dtn_portal_rule()

    accounts = [get_supplier_account(name) for name in supplier_names]

    if not accounts:
        return {}

    non_dtn_accounts = [
        account for account in accounts if account.portal_name != "dtn"
    ]

    if non_dtn_accounts:
        names = ", ".join(account.supplier_name for account in non_dtn_accounts)
        raise ValueError(f"Non-DTN suppliers passed to DTN group fetch: {names}")

    # CITGO and Valero share the DTN login. Use the first account for
    # credential loading and browser-session labeling.
    session_account = accounts[0]
    credentials = load_credentials(session_account)

    results: dict[str, FetchResult] = {}

    try:
        with open_browser_session(
            account=session_account,
            settings=settings,
            record_trace=True,
        ) as session:
            page = session.page

            login_to_dtn(
                page=page,
                login_url=portal_rule.login_url,
                username=credentials.username,
                password=credentials.password,
            )

            for account in accounts:
                try:
                    downloaded_files = capture_one_dtn_supplier_report_from_open_session(
                        page=page,
                        account=account,
                        business_date=business_date,
                        settings=settings,
                    )

                    stored_reports = [
                        download_manager.store_raw_report(
                            source_path=downloaded_file,
                            account=account,
                            business_date=business_date,
                            remove_source=remove_downloaded_files,
                        )
                        for downloaded_file in downloaded_files
                    ]

                    results[account.supplier_name] = make_success_fetch_result(
                        account=account,
                        business_date=business_date,
                        downloaded_files=downloaded_files,
                        stored_reports=stored_reports,
                    )

                except Exception as exc:
                    artifacts = capture_failure_artifacts(
                        page=page,
                        settings=settings,
                        account=account,
                        step_name="dtn_group_supplier_fetch_failed",
                    )

                    extra = {}

                    try:
                        target = get_dtn_report_target(account.supplier_name)
                        extra["visible_rows"] = summarize_dtn_rows(page)
                        extra["matching_rows"] = summarize_matching_rows(page, target)
                    except Exception:
                        pass

                    try:
                        diagnostic_path = write_exception_diagnostic(
                            account=account,
                            business_date=business_date,
                            step_name="dtn_group_supplier_fetch_failed",
                            exc=exc,
                            settings=settings,
                            page=page,
                            artifact_paths=artifacts,
                            extra=extra,
                        )
                        print(f"[DIAGNOSTIC] {diagnostic_path}")
                    except Exception:
                        pass

                    results[account.supplier_name] = make_failed_fetch_result(
                        account=account,
                        business_date=business_date,
                        error_message=str(exc),
                    )

                    # Continue to next DTN supplier. Each supplier capture reopens
                    # DataConnect, so the page can recover from report/detail view.

        return results

    except Exception as exc:
        # Login/session-level failure. Mark every requested DTN supplier failed.
        for account in accounts:
            results[account.supplier_name] = make_failed_fetch_result(
                account=account,
                business_date=business_date,
                error_message=str(exc),
            )

        return results