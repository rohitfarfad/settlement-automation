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
from settlement_automation.connectors.sunoco_date import (
    get_sunoco_settlement_date_for_business_date,
)
from settlement_automation.exceptions import PortalDownloadError


class SunocoPortalConnector(SupplierPortalConnector):
    """
    Fetches Sunoco settlement JSON reports.

    This connector is currently boilerplate only.

    Expected final behavior:
        1. Login to Sunoco portal.
        2. Navigate to settlement/report page.
        3. Select settlement date = business_date + 1 day.
        4. Capture raw JSON response.
        5. Save valid JSON text to data/tmp/sunoco/.
        6. Return temporary JSON file path.

    This connector must not parse, validate, reconcile, or write Excel output.
    """

    def __init__(self, account, settings: AppSettings | None = None):
        super().__init__(account)
        self.settings = settings or get_settings()

    def fetch_reports(self, business_date: date) -> list[Path]:
        portal_rule = get_sunoco_portal_rule()
        credentials = load_credentials(self.account)
        target = get_sunoco_report_target()
        settlement_date = get_sunoco_settlement_date_for_business_date(business_date)

        if not portal_rule.login_url:
            raise PortalDownloadError(
                "SUNOCO_LOGIN_URL is not configured. "
                "Add SUNOCO_LOGIN_URL to .env before running Sunoco fetch."
            )

        with open_browser_session(
            account=self.account,
            settings=self.settings,
            record_trace=True,
        ) as session:
            page = session.page

            try:
                return self._fetch_reports_from_portal(
                    page=page,
                    login_url=portal_rule.login_url,
                    reports_url=portal_rule.reports_url,
                    username=credentials.username,
                    password=credentials.password,
                    business_date=business_date,
                    settlement_date=settlement_date,
                    target=target,
                )

            except Exception:
                capture_failure_artifacts(
                    page=page,
                    settings=self.settings,
                    account=self.account,
                    step_name="sunoco_fetch_failed",
                )
                raise

    def _fetch_reports_from_portal(
        self,
        page,
        login_url: str,
        reports_url: str | None,
        username: str,
        password: str,
        business_date: date,
        settlement_date: date,
        target,
    ) -> list[Path]:
        """
        Placeholder for actual Sunoco browser flow.

        To implement after portal verification:
            - open login_url
            - login using username/password
            - verify authenticated session
            - navigate to reports page
            - select settlement_date
            - capture JSON response
            - call save_sunoco_json_text(...)
            - return [tmp_path]
        """
        raise NotImplementedError(
            "Sunoco portal flow is not implemented yet. "
            "Next step is to probe login and report navigation manually."
        )