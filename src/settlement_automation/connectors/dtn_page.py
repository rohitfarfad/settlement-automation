import time
from datetime import date

from config.dtn_reports import DTNReportTarget
from settlement_automation.connectors.dtn_date import format_dtn_dropdown_date
from settlement_automation.exceptions import PortalDownloadError


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