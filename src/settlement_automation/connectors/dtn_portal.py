from datetime import date
from pathlib import Path

from config.dtn_reports import get_dtn_report_target
from config.portal_rules import get_dtn_portal_rule
from config.settings import AppSettings, get_settings
from settlement_automation.connectors.base import SupplierPortalConnector
from settlement_automation.connectors.browser import (
    capture_failure_artifacts,
    open_browser_session,
)
from settlement_automation.connectors.credentials import load_credentials
from settlement_automation.connectors.dtn_capture import (
    capture_visible_dtn_report_text_from_row,
    save_dtn_report_text,
)
from settlement_automation.connectors.dtn_content_selection import (
    report_matches_required_content,
)
from settlement_automation.connectors.dtn_page import (
    find_matching_report_rows_by_text,
    login_to_dtn,
    open_dataconnect_direct,
    select_dataconnect_date,
    wait_for_dataconnect_rows,
)
from settlement_automation.exceptions import PortalDownloadError

from settlement_automation.services.diagnostics import write_exception_diagnostic
from settlement_automation.connectors.dtn_diagnostics import (
    summarize_dtn_rows,
    summarize_matching_rows,
)

class DTNPortalConnector(SupplierPortalConnector):
    """
    Fetches CITGO and Valero Credit Card Memo reports from DTN DataConnect.

    It captures visible raw report text from the DTN page.
    It does not parse, validate, reconcile, or write Excel output.
    """

    def __init__(self, account, settings: AppSettings | None = None):
        super().__init__(account)
        self.settings = settings or get_settings()

    def fetch_reports(self, business_date: date) -> list[Path]:
        portal_rule = get_dtn_portal_rule()
        credentials = load_credentials(self.account)
        target = get_dtn_report_target(self.account.supplier_name)

        with open_browser_session(
            account=self.account,
            settings=self.settings,
            record_trace=True,
        ) as session:
            page = session.page

            try:
                login_to_dtn(
                    page=page,
                    login_url=portal_rule.login_url,
                    username=credentials.username,
                    password=credentials.password,
                )

                open_dataconnect_direct(
                    page=page,
                    dataconnect_url=portal_rule.dataconnect_url,
                )

                select_dataconnect_date(
                    page=page,
                    business_date=business_date,
                )

                wait_for_dataconnect_rows(
                    page=page,
                    target=target,
                    timeout_seconds=60,
                )

                rows = find_matching_report_rows_by_text(page, target)

                if not rows:
                    raise PortalDownloadError(
                        f"No DTN rows found for supplier={self.account.supplier_name}, "
                        f"business_date={business_date}"
                    )

                last_captured_preview = ""

                for row_index in range(1, len(rows) + 1):
                    # Re-open the list fresh each time because clicking a row opens
                    # the report in the same page.
                    open_dataconnect_direct(
                        page=page,
                        dataconnect_url=portal_rule.dataconnect_url,
                    )

                    select_dataconnect_date(
                        page=page,
                        business_date=business_date,
                    )

                    wait_for_dataconnect_rows(
                        page=page,
                        target=target,
                        timeout_seconds=60,
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
                        settings=self.settings,
                        account=self.account,
                        target=target,
                        business_date=business_date,
                        row_index=row_index,
                    )

                    return [tmp_path]

                raise PortalDownloadError(
                    f"No DTN report content matched required markers for "
                    f"supplier={self.account.supplier_name}, business_date={business_date}. "
                    f"Last captured preview: {last_captured_preview!r}"
                )


            except Exception as exc:

                artifacts = capture_failure_artifacts(

                    page=page,

                    settings=self.settings,

                    account=self.account,

                    step_name="dtn_fetch_failed",

                )

                extra = {}

                try:

                    extra["visible_rows"] = summarize_dtn_rows(page)

                except Exception:

                    pass

                try:

                    extra["matching_rows"] = summarize_matching_rows(page, target)

                except Exception:

                    pass

                diagnostic_path = write_exception_diagnostic(

                    account=self.account,

                    business_date=business_date,

                    step_name="dtn_fetch_failed",

                    exc=exc,

                    settings=self.settings,

                    page=page,

                    artifact_paths=artifacts,

                    extra=extra,

                )

                print(f"[DIAGNOSTIC] {diagnostic_path}")

                raise