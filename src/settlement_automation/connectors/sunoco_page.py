import time

from settlement_automation.exceptions import PortalLoginError


USERNAME_SELECTORS = [
    'input[name="username"]',
    'input[name="userName"]',
    'input[name="userid"]',
    'input[name="userId"]',
    'input[name="email"]',
    'input[id="username"]',
    'input[id="userName"]',
    'input[id="userid"]',
    'input[id="email"]',
    'input[type="email"]',
    'input[type="text"]',
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
    'button:has-text("Submit")',
    'input[value="Sign in"]',
    'input[value="Sign In"]',
    'input[value="Login"]',
    'input[value="Submit"]',
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


def probe_sunoco_login_fields(page, login_url: str) -> dict:
    page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2000)

    username_input = first_visible_locator(page, USERNAME_SELECTORS)
    password_input = first_visible_locator(page, PASSWORD_SELECTORS)
    submit_button = first_visible_locator(page, SUBMIT_SELECTORS)

    return {
        "initial_url": page.url,
        "title": page.title(),
        "username_input_found": username_input is not None,
        "password_input_found": password_input is not None,
        "submit_button_found": submit_button is not None,
    }


def wait_for_sunoco_authenticated(page, timeout_seconds: int = 60) -> None:
    """
    Wait until Sunoco login appears successful.

    This is intentionally broad because we do not know the Sunoco portal markup yet.
    After running the login probe, tighten these markers if needed.
    """
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        current_url = page.url

        try:
            body_text = page.locator("body").inner_text(timeout=5000)
        except Exception:
            body_text = ""

        authenticated_markers = [
            "Sign Out",
            "Logout",
            "Log Out",
            "Dashboard",
            "Reports",
            "Settlement",
            "Account",
        ]

        login_markers = [
            "Password",
            "Sign In",
            "Login",
        ]

        if any(marker in body_text for marker in authenticated_markers):
            return

        # Useful fallback: password field disappeared and page no longer looks like login.
        try:
            password_fields = page.locator('input[type="password"]').count()
        except Exception:
            password_fields = 1

        if password_fields == 0 and not any(marker in body_text for marker in login_markers):
            return

        # If URL changed away from login page and password field is gone, likely authenticated.
        if password_fields == 0 and current_url:
            return

        page.wait_for_timeout(1000)

    raise PortalLoginError(
        f"Timed out waiting for Sunoco authenticated session. Current URL: {page.url}"
    )


def login_to_sunoco(page, login_url: str, username: str, password: str) -> None:
    page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2000)

    username_input = first_visible_locator(page, USERNAME_SELECTORS)
    password_input = first_visible_locator(page, PASSWORD_SELECTORS)
    submit_button = first_visible_locator(page, SUBMIT_SELECTORS)

    if username_input is None or password_input is None:
        raise PortalLoginError("Could not find Sunoco username/password fields.")

    username_input.fill(username)
    password_input.fill(password)

    if submit_button is not None:
        submit_button.click()
    else:
        password_input.press("Enter")

    wait_for_sunoco_authenticated(page, timeout_seconds=60)