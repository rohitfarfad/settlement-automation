from _path_setup import PROJECT_ROOT  # noqa: F401

import argparse

from config.portal_rules import get_sunoco_portal_rule
from config.settings import get_settings
from config.supplier_accounts import get_supplier_account
from settlement_automation.connectors.browser import (
    capture_failure_artifacts,
    open_browser_session,
)
from settlement_automation.connectors.credentials import load_credentials
from settlement_automation.connectors.sunoco_page import (
    login_to_sunoco,
    probe_sunoco_login_fields,
)
from settlement_automation.services.diagnostics import write_exception_diagnostic
from settlement_automation.utils.env import load_local_env


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Probe Sunoco login and authenticated session behavior."
    )

    parser.add_argument(
        "--login-url",
        default=None,
        help="Optional Sunoco login URL override.",
    )

    parser.add_argument(
        "--attempt-login",
        action="store_true",
        help="Actually fill credentials and submit login form.",
    )

    parser.add_argument(
        "--pause",
        action="store_true",
        help="Pause after login/field detection for manual inspection.",
    )

    parser.add_argument(
        "--print-page-text",
        action="store_true",
        help="Print visible page text. Avoid using if page has sensitive data.",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    settings = get_settings()
    load_local_env(settings.project_root)

    account = get_supplier_account("sunoco")
    portal_rule = get_sunoco_portal_rule()
    login_url = args.login_url or portal_rule.login_url

    if not login_url:
        print("[FAILED] SUNOCO_LOGIN_URL is not configured.")
        print("Add SUNOCO_LOGIN_URL to .env or pass --login-url.")
        return 1

    print(f"[INFO] supplier={account.supplier_name}")
    print(f"[INFO] portal={account.portal_name}")
    print(f"[INFO] login_url={login_url}")
    print(f"[INFO] attempt_login={args.attempt_login}")

    try:
        with open_browser_session(
            account=account,
            settings=settings,
            record_trace=False,
        ) as session:
            page = session.page

            print("[STEP] Probing Sunoco login fields...")
            probe_result = probe_sunoco_login_fields(
                page=page,
                login_url=login_url,
            )

            print(f"[INFO] initial_url={probe_result['initial_url']}")
            print(f"[INFO] title={probe_result['title']}")
            print(f"[CHECK] username_input_found={probe_result['username_input_found']}")
            print(f"[CHECK] password_input_found={probe_result['password_input_found']}")
            print(f"[CHECK] submit_button_found={probe_result['submit_button_found']}")

            if not args.attempt_login:
                if args.print_page_text:
                    print("\n========== PAGE TEXT START ==========")
                    print(page.locator("body").inner_text(timeout=10000))
                    print("========== PAGE TEXT END ==========\n")

                if args.pause:
                    print("[INFO] Pausing for manual inspection.")
                    page.pause()

                print("[SUCCESS] Login field probe completed. Login was not attempted.")
                return 0

            print("[STEP] Loading Sunoco credentials...")
            credentials = load_credentials(account)

            print("[STEP] Attempting Sunoco login...")
            login_to_sunoco(
                page=page,
                login_url=login_url,
                username=credentials.username,
                password=credentials.password,
            )

            print("[SUCCESS] Sunoco login appears successful.")
            print(f"[INFO] after_login_url={page.url}")
            print(f"[INFO] after_login_title={page.title()}")

            if args.print_page_text:
                print("\n========== PAGE TEXT START ==========")
                print(page.locator("body").inner_text(timeout=10000))
                print("========== PAGE TEXT END ==========\n")

            if args.pause:
                print("[INFO] Pausing after login for manual inspection.")
                page.pause()

            return 0

    except Exception as exc:
        print(f"[FAILED] Sunoco login probe failed: {exc}")

        artifacts = {}
        try:
            artifacts = capture_failure_artifacts(
                page=page,
                settings=settings,
                account=account,
                step_name="sunoco_login_probe_failed",
            )
        except Exception:
            pass

        try:
            diagnostic_path = write_exception_diagnostic(
                account=account,
                business_date="login_probe",
                step_name="sunoco_login_probe_failed",
                exc=exc,
                settings=settings,
                page=page if "page" in locals() else None,
                artifact_paths=artifacts,
                extra={
                    "login_url": login_url,
                    "attempt_login": args.attempt_login,
                },
            )
            print(f"[DIAGNOSTIC] {diagnostic_path}")
        except Exception:
            pass

        return 1


if __name__ == "__main__":
    raise SystemExit(main())