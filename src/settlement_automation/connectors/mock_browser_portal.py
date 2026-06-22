from datetime import date
from pathlib import Path

from config.settings import AppSettings, get_settings
from settlement_automation.connectors.base import SupplierPortalConnector
from settlement_automation.connectors.browser import open_browser_session
from settlement_automation.exceptions import PortalDownloadError
from settlement_automation.utils.files import ensure_directory


class MockBrowserPortalConnector(SupplierPortalConnector):
    """
    Browser-based fake connector used to test Playwright download behavior.

    This does not access any supplier website.
    """

    def __init__(self, account, settings: AppSettings | None = None):
        super().__init__(account)
        self.settings = settings or get_settings()

    def fetch_reports(self, business_date: date) -> list[Path]:
        with open_browser_session(
            account=self.account,
            settings=self.settings,
            record_trace=False,
        ) as session:
            page = session.page
            download_dir = session.download_dir
            ensure_directory(download_dir)

            file_name = (
                f"{self.account.supplier_name}_mock_"
                f"{business_date.isoformat()}.txt"
            )

            report_content = (
                f"Mock report\n"
                f"supplier={self.account.supplier_name}\n"
                f"portal={self.account.portal_name}\n"
                f"business_date={business_date.isoformat()}\n"
            )

            html = f"""
            <html>
              <body>
                <a
                  id="download-report"
                  download="{file_name}"
                  href="data:text/plain;charset=utf-8,{report_content}"
                >
                  Download report
                </a>
              </body>
            </html>
            """

            page.set_content(html)

            try:
                with page.expect_download() as download_info:
                    page.locator("#download-report").click()

                download = download_info.value
                downloaded_path = download_dir / file_name
                download.save_as(str(downloaded_path))

            except Exception as exc:
                raise PortalDownloadError(
                    f"Mock browser download failed for supplier={self.account.supplier_name}"
                ) from exc

            return [downloaded_path]