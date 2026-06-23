from _path_setup import PROJECT_ROOT  # noqa: F401

import argparse
import json
from datetime import date, timedelta

from config.portal_rules import get_sunoco_portal_rule
from config.settings import get_settings
from config.supplier_accounts import get_supplier_account
from config.sunoco_reports import get_sunoco_report_target
from settlement_automation.connectors.browser import (
    capture_failure_artifacts,
    open_browser_session,
)
from settlement_automation.connectors.credentials import load_credentials
from settlement_automation.connectors.sunoco_capture import save_sunoco_json_text
from settlement_automation.connectors.sunoco_date import get_sunoco_portal_request_date
from settlement_automation.connectors.sunoco_page import login_to_sunoco
from settlement_automation.services.diagnostics import write_exception_diagnostic
from settlement_automation.utils.env import load_local_env


DATE_INPUT_SELECTORS = [
    'input[name*="from" i]',
    'input[id*="from" i]',
    'input[name*="start" i]',
    'input[id*="start" i]',
    'input[name*="begin" i]',
    'input[id*="begin" i]',
    'input[type="date"]',
    'input[type="text"]',
]


TO_DATE_INPUT_SELECTORS = [
    'input[name*="to" i]',
    'input[id*="to" i]',
    'input[name*="end" i]',
    'input[id*="end" i]',
    'input[type="date"]',
    'input[type="text"]',
]


SEARCH_BUTTON_SELECTORS = [
    'button:has-text("Search")',
    'input[value="Search"]',
    'button[type="submit"]',
    'input[type="submit"]',
]


def parse_business_date(value: str) -> date:
    return date.fromisoformat(value)


def format_sunoco_date(value: date) -> str:
    """
    First guess. We may adjust after probing the actual field behavior.
    """
    return value.strftime("%m/%d/%Y")


def first_visible_locator(page, selectors: list[str]):
    for selector in selectors:
        locator = page.locator(selector)

        try:
            if locator.count() > 0 and locator.first.is_visible():
                return locator.first
        except Exception:
            continue

    return None


def looks_like_sunoco_json_response(url: str, text: str) -> bool:
    lowered_url = url.lower()

    if "settlement" not in lowered_url and "credit" not in lowered_url:
        return False

    try:
        parsed = json.loads(text)
    except Exception:
        return False

    serialized = json.dumps(parsed)

    return (
        "totalSalesAmount" in serialized
        or "totalDealerFeeAmount" in serialized
        or "settlementDate" in serialized
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Probe Sunoco settlement search and JSON response capture."
    )

    parser.add_argument(
        "--business-date",
        type=parse_business_date,
        default=date.today() - timedelta(days=1),
        help="Business date. Sunoco portal search uses business_date + 1.",
    )

    parser.add_argument(
        "--login-url",
        default=None,
    )

    parser.add_argument(
        "--reports-url",
        default=None,
    )

    parser.add_argument(
        "--pause-before-search",
        action="store_true",
    )

    parser.add_argument(
        "--pause-after-search",
        action="store_true",
    )

    parser.add_argument(
        "--print-page-text",
        action="store_true",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    settings = get_settings()
    load_local_env(settings.project_root)

    account = get_supplier_account("sunoco")
    credentials = load_credentials(account)
    portal_rule = get_sunoco_portal_rule()
    target = get_sunoco_report_target()

    login_url = args.login_url or portal_rule.login_url
    reports_url = args.reports_url or portal_rule.reports_url

    settlement_date = get_sunoco_portal_request_date(args.business_date)
    settlement_date_text = format_sunoco_date(settlement_date)

    print(f"[INFO] supplier={account.supplier_name}")
    print(f"[INFO] login_url={login_url}")
    print(f"[INFO] reports_url={reports_url}")
    print(f"[INFO] business_date={args.business_date}")
    print(f"[INFO] portal_settlement_date={settlement_date}")
    print(f"[INFO] date_input_text={settlement_date_text}")

    json_candidates: list[tuple[str, str]] = []

    def record_response(response):
        url = response.url

        if "portal.sunocolp.com" not in url:
            return

        try:
            text = response.text()
        except Exception:
            return

        if looks_like_sunoco_json_response(url, text):
            json_candidates.append((url, text))

    try:
        with open_browser_session(
            account=account,
            settings=settings,
            record_trace=False,
        ) as session:
            page = session.page
            page.on("response", record_response)

            print("[STEP] Logging into Sunoco...")
            login_to_sunoco(
                page=page,
                login_url=login_url,
                username=credentials.username,
                password=credentials.password,
            )

            print(f"[INFO] after_login_url={page.url}")
            print(f"[INFO] after_login_title={page.title()}")

            print("[STEP] Opening settlement page...")
            page.goto(reports_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)

            print(f"[INFO] settlement_page_url={page.url}")
            print(f"[INFO] settlement_page_title={page.title()}")

            if args.print_page_text:
                print("\n========== PAGE TEXT START ==========")
                print(page.locator("body").inner_text(timeout=10000))
                print("========== PAGE TEXT END ==========\n")

            from_date_input = first_visible_locator(page, DATE_INPUT_SELECTORS)
            to_date_input = first_visible_locator(page, TO_DATE_INPUT_SELECTORS)
            search_button = first_visible_locator(page, SEARCH_BUTTON_SELECTORS)

            print(f"[CHECK] from_date_input_found={from_date_input is not None}")
            print(f"[CHECK] to_date_input_found={to_date_input is not None}")
            print(f"[CHECK] search_button_found={search_button is not None}")

            if from_date_input is None or to_date_input is None:
                print("[FAILED] Could not find Sunoco from/to date inputs.")
                return 1

            if args.pause_before_search:
                print("[INFO] Pausing before search.")
                page.pause()

            print("[STEP] Filling settlement date range...")
            from_date_input.fill(settlement_date_text)
            to_date_input.fill(settlement_date_text)

            print("[STEP] Clicking Search...")
            if search_button is not None:
                search_button.click()
            else:
                to_date_input.press("Enter")

            page.wait_for_timeout(8000)

            if args.pause_after_search:
                print("[INFO] Pausing after search.")
                page.pause()

            print(f"[INFO] json_candidates_found={len(json_candidates)}")

            for index, (url, text) in enumerate(json_candidates, start=1):
                print(f"[JSON {index}] url={url}")
                print(f"[JSON {index}] size_bytes={len(text.encode('utf-8'))}")

            if not json_candidates:
                print("[FAILED] No Sunoco settlement JSON response was captured.")
                return 1

            selected_url, selected_json = json_candidates[-1]

            print(f"[STEP] Saving captured Sunoco JSON from: {selected_url}")

            tmp_path = save_sunoco_json_text(
                json_text=selected_json,
                settings=settings,
                account=account,
                business_date=args.business_date,
                settlement_date=settlement_date,
                target=target,
            )

            print("[SUCCESS] Captured and saved Sunoco JSON.")
            print(f"[INFO] tmp_path={tmp_path}")
            print(f"[INFO] size_bytes={tmp_path.stat().st_size}")

            return 0

    except Exception as exc:
        print(f"[FAILED] Sunoco settlement probe failed: {exc}")

        artifacts = {}
        try:
            artifacts = capture_failure_artifacts(
                page=page,
                settings=settings,
                account=account,
                step_name="sunoco_settlement_probe_failed",
            )
        except Exception:
            pass

        try:
            diagnostic_path = write_exception_diagnostic(
                account=account,
                business_date=args.business_date,
                step_name="sunoco_settlement_probe_failed",
                exc=exc,
                settings=settings,
                page=page if "page" in locals() else None,
                artifact_paths=artifacts,
                extra={
                    "login_url": login_url,
                    "reports_url": reports_url,
                    "settlement_date": str(settlement_date),
                    "json_candidates_count": len(json_candidates),
                },
            )
            print(f"[DIAGNOSTIC] {diagnostic_path}")
        except Exception:
            pass

        return 1


if __name__ == "__main__":
    raise SystemExit(main())