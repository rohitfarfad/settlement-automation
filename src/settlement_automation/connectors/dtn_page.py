import time
from datetime import date

from config.dtn_reports import DTNReportTarget
from settlement_automation.connectors.dtn_date import format_dtn_dropdown_date
from settlement_automation.exceptions import PortalDownloadError

from pathlib import Path

from config.settings import AppSettings
from config.supplier_accounts import SupplierAccount
from settlement_automation.connectors.dtn_capture import (
    CapturedDTNReport,
    build_dtn_tmp_report_path,
    is_likely_dtn_message_response,
    write_response_body_to_tmp_file,
)

from settlement_automation.connectors.dtn_capture import (
    DTNReportLink,
    normalize_dtn_url,
)

USERNAME_SELECTORS = [
    'input[name="username"]',
    'input[name="userName"]',
    'input[name="userid"]',
    'input[name="userId"]',
    'input[id="username"]',
    'input[id="userName"]',
    'input[id="userid"]',
    'input[type="text"]',
    'input[type="email"]',
]

PASSWORD_SELECTORS = [
    'input[name="password"]',
    'input[id="password"]',
    'input[type="password"]',
]

SUBMIT_SELECTORS = [
    'button[type="submit"]',
    'input[type="submit"]',
    'button:has-text("Sign in")',
    'button:has-text("Sign In")',
    'button:has-text("Login")',
    'button:has-text("Log in")',
    'input[value="Sign in"]',
    'input[value="Sign In"]',
    'input[value="Login"]',
]


def first_visible_locator(page, selectors: list[str]):
    for selector in selectors:
        locator = page.locator(selector)

        try:
            if locator.count() > 0 and locator.first.is_visible():
                return locator.first
        except Exception:
            continue

    return None


def wait_for_dtn_authenticated(page, timeout_seconds: int = 60) -> None:
    """
    Wait until DTN login has succeeded.

    Do not wait for full network idle. The DTN portal can keep background
    requests active, so we only wait for authentication/session indicators.
    """
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        current_url = page.url

        try:
            body_text = get_visible_table_like_text(page)
        except Exception:
            body_text = ""

        authenticated_markers = [
            "Sign Out",
            "Markets",
            "DataConnect",
            "Settings",
        ]

        if "/energy/common/" in current_url:
            return

        if any(marker in body_text for marker in authenticated_markers):
            return

        # If the password field is gone, that is also a useful signal.
        try:
            password_fields = page.locator('input[type="password"]').count()
            if password_fields == 0 and "fuelbuyer.dtn.com/energy" in current_url:
                return
        except Exception:
            pass

        page.wait_for_timeout(1000)

    raise PortalDownloadError(
        f"Timed out waiting for DTN authenticated session. Current URL: {page.url}"
    )


def login_to_dtn(page, login_url: str, username: str, password: str) -> None:
    page.goto(login_url, wait_until="domcontentloaded", timeout=60000)

    username_input = first_visible_locator(page, USERNAME_SELECTORS)
    password_input = first_visible_locator(page, PASSWORD_SELECTORS)
    submit_button = first_visible_locator(page, SUBMIT_SELECTORS)

    if username_input is None or password_input is None:
        raise PortalDownloadError("Could not find DTN username/password fields.")

    username_input.fill(username)
    password_input.fill(password)

    if submit_button is not None:
        submit_button.click()
    else:
        password_input.press("Enter")

    wait_for_dtn_authenticated(page, timeout_seconds=60)

def open_dataconnect_tab(page, dataconnect_url: str | None = None) -> None:
    """
    Open the DTN DataConnect page after login.

    Preferred approach:
    - Navigate directly to the known DataConnect URL.

    Fallback:
    - Click the DataConnect tab if direct navigation is not provided.
    """
    if dataconnect_url:
        page.goto(dataconnect_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_load_state("networkidle", timeout=60000)

        body_text = get_visible_table_like_text(page)
        if "DataConnect Messages" in body_text or "Message List" in body_text:
            return

    candidates = [
        page.get_by_role("link", name="DataConnect"),
        page.get_by_role("button", name="DataConnect"),
        page.get_by_text("DataConnect", exact=True),
        page.locator("a:has-text('DataConnect')"),
        page.locator("button:has-text('DataConnect')"),
    ]

    for locator in candidates:
        try:
            if locator.count() > 0 and locator.first.is_visible():
                locator.first.click()
                page.wait_for_load_state("networkidle", timeout=60000)
                page.wait_for_timeout(1000)
                return
        except Exception:
            continue

    raise PortalDownloadError("Could not find or open DTN DataConnect page.")


def select_dataconnect_date(page, business_date: date) -> str:
    """
    Select the requested date in the DataConnect date dropdown.

    Changing this dropdown triggers the table reload.
    Do not click Refresh after this, because Refresh resets the date.
    """
    dtn_date_label = format_dtn_dropdown_date(business_date)

    select_candidates = [
        page.locator("select[name*='date' i]").first,
        page.locator("select[id*='date' i]").first,
        page.locator("select").first,
    ]

    last_error = None

    for select in select_candidates:
        try:
            if select.count() > 0 and select.is_visible():
                select.select_option(label=dtn_date_label)

                try:
                    select.dispatch_event("input")
                    select.dispatch_event("change")
                except Exception:
                    pass

                page.wait_for_timeout(2000)
                return dtn_date_label

        except Exception as exc:
            last_error = exc

    raise PortalDownloadError(
        f"Could not select DTN date option: {dtn_date_label}. Last error: {last_error}"
    )

def get_visible_table_like_text(page) -> str:
    """
    Return body text for debugging/report-row discovery.

    This should not be logged permanently in production because the dashboard may
    contain sensitive report metadata. It is only for local probe/debug.
    """
    try:
        return page.locator("body").inner_text(timeout=10000)
    except Exception:
        return ""


def find_report_row_by_text(page, target: DTNReportTarget):
    rows = find_matching_report_rows_by_text(page, target)
    return rows[0] if rows else None

def click_dataconnect_refresh(page) -> bool:
    """
    Click the DataConnect Refresh button if it is visible.

    Returns True if a refresh button was found and clicked.
    """
    candidates = [
        page.get_by_role("button", name="Refresh"),
        page.get_by_text("Refresh", exact=True),
        page.locator("input[value='Refresh']"),
        page.locator("button:has-text('Refresh')"),
        page.locator("a:has-text('Refresh')"),
    ]

    for locator in candidates:
        try:
            if locator.count() > 0 and locator.first.is_visible():
                locator.first.click()
                return True
        except Exception:
            continue

    return False


def wait_for_dataconnect_rows(
    page,
    target: DTNReportTarget | None = None,
    timeout_seconds: int = 60,
) -> None:
    """
    Wait for the DataConnect message table to load after the date dropdown changes.

    If target is provided, wait specifically until the target supplier/report name
    appears in the page text.
    """
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        body_text = get_visible_table_like_text(page)
        normalized = " ".join(body_text.split())

        if target is not None:
            if target.report_name in normalized:
                return
        else:
            loading_present = "Loading..." in normalized or "Loading" in normalized

            if not loading_present and "Message List" in normalized:
                return

        page.wait_for_timeout(1000)

    raise PortalDownloadError(
        f"Timed out waiting for DTN DataConnect rows to load. "
        f"Target={target.report_name if target else 'unknown'}"
    )

def find_matching_report_rows_by_text(page, target: DTNReportTarget) -> list:
    """
    Find clean DTN message table rows matching the configured supplier target.

    The previous broad tr search could accidentally match a large layout row
    containing the entire page. This function filters out layout/header rows and
    keeps only compact rows that look like actual message-table rows.
    """
    selectors = [
        "table.dataTable tbody tr",
        "table[id*='message' i] tbody tr",
        "table[id*='data' i] tbody tr",
        "tbody tr",
        "tr",
    ]

    matches = []
    seen_texts = set()

    for selector in selectors:
        rows = page.locator(selector)

        try:
            count = rows.count()
        except Exception:
            continue

        for index in range(count):
            row = rows.nth(index)

            try:
                text = row.inner_text(timeout=3000)
            except Exception:
                continue

            normalized = " ".join(text.split())

            if not normalized:
                continue

            if normalized in seen_texts:
                continue

            # Skip large layout rows that contain the whole page.
            if len(normalized) > 500:
                continue

            # Skip header rows.
            if "Supplier Received Date Group Document" in normalized:
                continue

            # Actual target match.
            if (
                target.report_name in normalized
                and target.report_group in normalized
                and target.document_name in normalized
            ):
                matches.append(row)
                seen_texts.add(normalized)

        if matches:
            return matches

    return matches


def extract_matching_dtn_report_links(
    page,
    target: DTNReportTarget,
    business_date: date,
) -> list[DTNReportLink]:
    """
    Extract report links from all matching DTN message rows.

    For CITGO, there may be multiple Credit Card Memo rows for the same day.
    We capture all matching rows first and decide later which parsed data matters.
    """
    rows = find_matching_report_rows_by_text(page, target)
    report_links: list[DTNReportLink] = []

    for index, row in enumerate(rows, start=1):
        try:
            row_text = " ".join(row.inner_text(timeout=5000).split())
        except Exception:
            row_text = ""

        links = row.locator("a")
        href = None

        try:
            link_count = links.count()
        except Exception:
            link_count = 0

        for link_index in range(link_count):
            link = links.nth(link_index)

            try:
                candidate_href = link.get_attribute("href")
            except Exception:
                continue

            if not candidate_href:
                continue

            if "link.do" in candidate_href and "contentId=" in candidate_href:
                href = candidate_href
                break

        if href is None:
            continue

        absolute_url = normalize_dtn_url(page.url, href)

        report_links.append(
            DTNReportLink(
                supplier_name=target.supplier_name,
                business_date=business_date,
                row_index=index,
                row_text=row_text,
                url=absolute_url,
            )
        )

    return report_links


def find_clickable_report_element(row):
    """
    Find the clickable element inside a DTN message row.

    Usually the supplier/document text is a link. If no link is found,
    fall back to clicking the row itself.
    """
    link = row.locator("a").first

    try:
        if link.count() > 0 and link.is_visible():
            return link
    except Exception:
        pass

    return row


def capture_dtn_report_from_row(
    page,
    row,
    account: SupplierAccount,
    target: DTNReportTarget,
    business_date: date,
    row_index: int,
    settings: AppSettings,
) -> CapturedDTNReport:
    """
    Click one DTN message row/link and capture the resulting message response.

    This mirrors the manual process where you clicked a message and copied the
    response body from the browser Network tab.
    """
    clickable = find_clickable_report_element(row)
    tmp_path = build_dtn_tmp_report_path(
        settings=settings,
        account=account,
        target=target,
        business_date=business_date,
        row_index=row_index,
    )

    try:
        with page.expect_response(
            lambda response: is_likely_dtn_message_response(response.url),
            timeout=60000,
        ) as response_info:
            clickable.click()

        response = response_info.value
        write_response_body_to_tmp_file(response=response, tmp_path=tmp_path)

        return CapturedDTNReport(
            supplier_name=account.supplier_name,
            business_date=business_date,
            row_index=row_index,
            source_url=response.url,
            tmp_path=tmp_path,
            size_bytes=tmp_path.stat().st_size,
        )

    except Exception as exc:
        raise PortalDownloadError(
            f"Failed to capture DTN report content for "
            f"supplier={account.supplier_name}, row_index={row_index}"
        ) from exc


def capture_matching_dtn_reports(
    page,
    account: SupplierAccount,
    target: DTNReportTarget,
    business_date: date,
    settings: AppSettings,
) -> list[CapturedDTNReport]:
    rows = find_matching_report_rows_by_text(page, target)

    if not rows:
        raise PortalDownloadError(
            f"No matching DTN report rows found for supplier={account.supplier_name}, "
            f"target={target.report_name} / {target.report_group} / {target.document_name}"
        )

    captured_reports = []

    for index, row in enumerate(rows, start=1):
        captured = capture_dtn_report_from_row(
            page=page,
            row=row,
            account=account,
            target=target,
            business_date=business_date,
            row_index=index,
            settings=settings,
        )
        captured_reports.append(captured)

    return captured_reports

def open_dataconnect_direct(page, dataconnect_url: str) -> None:
    """
    Open the stable DTN DataConnect URL after authentication.

    This assumes login has already completed and the browser context has
    the authenticated DTN session cookies.
    """
    page.goto(dataconnect_url, wait_until="domcontentloaded", timeout=60000)

    deadline = time.time() + 60

    while time.time() < deadline:
        body_text = get_visible_table_like_text(page)

        if "DataConnect Messages" in body_text or "Message List" in body_text:
            return

        # Some DTN pages show the shell first and hydrate the content slowly.
        page.wait_for_timeout(1000)

    raise PortalDownloadError(
        f"DataConnect page did not become ready after direct navigation. "
        f"Current URL: {page.url}"
    )