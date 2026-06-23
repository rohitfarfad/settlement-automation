from datetime import date
from pathlib import Path

from config.portal_rules import get_sunoco_portal_rule
from config.settings import AppSettings, get_settings
from config.sunoco_reports import get_sunoco_report_target
from settlement_automation.connectors.base import SupplierPortalConnector
from settlement_automation.connectors.browser import (
    capture_failure_artifacts,
    open_browser_session,
)
from settlement_automation.connectors.credentials import load_credentials
from settlement_automation.connectors.sunoco_api import (
    fetch_sunoco_settlement_json_text,
    is_sunoco_settlement_api_url,
)
from settlement_automation.connectors.sunoco_capture import save_sunoco_json_text
from settlement_automation.connectors.sunoco_date import get_sunoco_portal_request_date
from settlement_automation.connectors.sunoco_page import login_to_sunoco
from settlement_automation.exceptions import PortalDownloadError
from settlement_automation.services.diagnostics import write_exception_diagnostic


class SunocoPortalConnector(SupplierPortalConnector):
    """
    Fetches Sunoco credit card settlement summary data.

    Flow:
        1. Login to Sunoco portal.
        2. Open the Credit Card Settlement page.
        3. Capture a real frontend SettlementSummary API request.
        4. Reuse the captured auth headers.
        5. Request exact settlement date data from the API.
        6. Save valid JSON text as .txt.
        7. Return temporary file path.

    This connector only fetches raw report data.
    It does not parse, validate, reconcile, or write Excel output.
    """

    def __init__(self, account, settings: AppSettings | None = None):
        super().__init__(account)
        self.settings = settings or get_settings()

    def fetch_reports(self, business_date: date) -> list[Path]:
        portal_rule = get_sunoco_portal_rule()
        credentials = load_credentials(self.account)
        target = get_sunoco_report_target()

        login_url = portal_rule.login_url
        reports_url = portal_rule.reports_url

        if not login_url:
            raise PortalDownloadError(
                "SUNOCO_LOGIN_URL is not configured. "
                "Add SUNOCO_LOGIN_URL to .env."
            )

        if not reports_url:
            raise PortalDownloadError(
                "SUNOCO_REPORTS_URL is not configured. "
                "Add SUNOCO_REPORTS_URL to .env."
            )

        settlement_date = get_sunoco_portal_request_date(business_date)

        captured_settlement_headers: dict[str, str] | None = None
        captured_settlement_url: str | None = None

        def record_request(request):
            nonlocal captured_settlement_headers
            nonlocal captured_settlement_url

            url = request.url

            if not is_sunoco_settlement_api_url(url):
                return

            try:
                captured_settlement_headers = dict(request.headers)
                captured_settlement_url = url
            except Exception:
                return

        with open_browser_session(
            account=self.account,
            settings=self.settings,
            record_trace=True,
        ) as session:
            page = session.page
            page.on("request", record_request)

            try:
                login_to_sunoco(
                    page=page,
                    login_url=login_url,
                    username=credentials.username,
                    password=credentials.password,
                )

                page.goto(
                    reports_url,
                    wait_until="domcontentloaded",
                    timeout=60000,
                )

                # Let the Sunoco frontend make its default SettlementSummary
                # API calls so we can capture the authorization headers.
                page.wait_for_timeout(8000)

                if not captured_settlement_headers:
                    raise PortalDownloadError(
                        "No Sunoco SettlementSummary API request headers were captured. "
                        "The settlement page may not have loaded the table, or the API "
                        "endpoint may have changed."
                    )

                json_text = fetch_sunoco_settlement_json_text(
                    page=page,
                    settlement_date=settlement_date,
                    auth_headers=captured_settlement_headers,
                )

                tmp_path = save_sunoco_json_text(
                    json_text=json_text,
                    settings=self.settings,
                    account=self.account,
                    business_date=business_date,
                    settlement_date=settlement_date,
                    target=target,
                )

                return [tmp_path]

            except Exception as exc:
                artifacts = capture_failure_artifacts(
                    page=page,
                    settings=self.settings,
                    account=self.account,
                    step_name="sunoco_fetch_failed",
                )

                try:
                    diagnostic_path = write_exception_diagnostic(
                        account=self.account,
                        business_date=business_date,
                        step_name="sunoco_fetch_failed",
                        exc=exc,
                        settings=self.settings,
                        page=page,
                        artifact_paths=artifacts,
                        extra={
                            "login_url": login_url,
                            "reports_url": reports_url,
                            "settlement_date": str(settlement_date),
                            "captured_settlement_url": captured_settlement_url,
                            "captured_headers_found": captured_settlement_headers
                            is not None,
                        },
                    )
                    print(f"[DIAGNOSTIC] {diagnostic_path}")
                except Exception:
                    pass

                raise