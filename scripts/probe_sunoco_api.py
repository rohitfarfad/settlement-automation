from _path_setup import PROJECT_ROOT  # noqa: F401

import argparse
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
from settlement_automation.connectors.sunoco_api import (
    fetch_sunoco_settlement_json_text,
    is_sunoco_settlement_api_url,
)
from settlement_automation.connectors.sunoco_capture import save_sunoco_json_text
from settlement_automation.connectors.sunoco_date import get_sunoco_portal_request_date
from settlement_automation.connectors.sunoco_page import login_to_sunoco
from settlement_automation.services.diagnostics import write_exception_diagnostic
from settlement_automation.utils.env import load_local_env


def parse_business_date(value: str) -> date:
    return date.fromisoformat(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Probe Sunoco settlement JSON API using authenticated frontend request headers."
    )

    parser.add_argument(
        "--business-date",
        type=parse_business_date,
        default=date.today() - timedelta(days=1),
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
        "--pause-after-settlement-page",
        action="store_true",
    )

    return parser


def redact_sensitive_headers(headers: dict[str, str]) -> dict[str, str]:
    redacted = {}

    sensitive_fragments = [
        "authorization",
        "cookie",
        "token",
        "jwt",
        "x-xsrf",
        "x-csrf",
    ]

    for key, value in headers.items():
        lower_key = key.lower()

        if any(fragment in lower_key for fragment in sensitive_fragments):
            redacted[key] = "***"
        else:
            redacted[key] = value

    return redacted


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

    print(f"[INFO] supplier={account.supplier_name}")
    print(f"[INFO] login_url={login_url}")
    print(f"[INFO] reports_url={reports_url}")
    print(f"[INFO] business_date={args.business_date}")
    print(f"[INFO] portal_settlement_date={settlement_date}")

    captured_settlement_headers = None
    captured_settlement_url = None

    def record_request(request):
        nonlocal captured_settlement_headers
        nonlocal captured_settlement_url

        url = request.url

        if not is_sunoco_settlement_api_url(url):
            return

        try:
            headers = request.headers
        except Exception:
            return

        captured_settlement_headers = dict(headers)
        captured_settlement_url = url

    try:
        with open_browser_session(
            account=account,
            settings=settings,
            record_trace=False,
        ) as session:
            page = session.page
            page.on("request", record_request)

            print("[STEP] Logging into Sunoco...")
            login_to_sunoco(
                page=page,
                login_url=login_url,
                username=credentials.username,
                password=credentials.password,
            )

            print(f"[INFO] after_login_url={page.url}")
            print(f"[INFO] after_login_title={page.title()}")

            print("[STEP] Opening Sunoco settlement page to capture frontend API auth headers...")
            page.goto(reports_url, wait_until="domcontentloaded", timeout=60000)

            # Give the frontend time to make its default SettlementSummary API call.
            page.wait_for_timeout(8000)

            print(f"[INFO] settlement_page_url={page.url}")
            print(f"[INFO] settlement_page_title={page.title()}")

            if args.pause_after_settlement_page:
                print("[INFO] Pausing after settlement page load.")
                page.pause()

            if not captured_settlement_headers:
                print("[FAILED] No SettlementSummary API request headers were captured.")
                print("[INFO] Try opening the page headed and verify the table loads.")
                return 1

            print("[SUCCESS] Captured SettlementSummary API request headers.")
            print(f"[INFO] captured_request_url={captured_settlement_url}")
            print("[INFO] captured_request_headers_redacted:")
            for key, value in redact_sensitive_headers(captured_settlement_headers).items():
                print(f"  {key}: {value}")

            print("[STEP] Fetching exact-date Sunoco settlement JSON using captured headers...")
            json_text = fetch_sunoco_settlement_json_text(
                page=page,
                settlement_date=settlement_date,
                auth_headers=captured_settlement_headers,
            )

            print("[STEP] Saving captured Sunoco JSON...")
            tmp_path = save_sunoco_json_text(
                json_text=json_text,
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
        print(f"[FAILED] Sunoco API probe failed: {exc}")

        artifacts = {}
        try:
            artifacts = capture_failure_artifacts(
                page=page,
                settings=settings,
                account=account,
                step_name="sunoco_api_probe_failed",
            )
        except Exception:
            pass

        try:
            diagnostic_path = write_exception_diagnostic(
                account=account,
                business_date=args.business_date,
                step_name="sunoco_api_probe_failed",
                exc=exc,
                settings=settings,
                page=page if "page" in locals() else None,
                artifact_paths=artifacts,
                extra={
                    "login_url": login_url,
                    "reports_url": reports_url,
                    "settlement_date": str(settlement_date),
                    "captured_settlement_url": captured_settlement_url,
                    "captured_headers_found": captured_settlement_headers is not None,
                },
            )
            print(f"[DIAGNOSTIC] {diagnostic_path}")
        except Exception:
            pass

        return 1


if __name__ == "__main__":
    raise SystemExit(main())