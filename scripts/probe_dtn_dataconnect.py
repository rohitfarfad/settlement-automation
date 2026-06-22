DEFAULT_DTN_DATACONNECT_URL = (
    "https://fuelbuyer.dtn.com/energy/common/link.do?contentId=750701&parentId=-1"
)
from _path_setup import PROJECT_ROOT  # noqa: F401

import argparse
from datetime import date, timedelta

from config.dtn_reports import get_dtn_report_target
from config.portal_rules import get_dtn_portal_rule
from config.settings import get_settings
from config.supplier_accounts import get_supplier_account
from settlement_automation.connectors.browser import (
    capture_failure_artifacts,
    open_browser_session,
)
from settlement_automation.connectors.credentials import load_credentials
from settlement_automation.connectors.dtn_page import (
    find_report_row_by_text,
    get_visible_table_like_text,
    login_to_dtn,
    open_dataconnect_direct,
    select_dataconnect_date,
    wait_for_dataconnect_rows,
)
from settlement_automation.utils.env import load_local_env


def parse_business_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid date: {value}. Expected format: YYYY-MM-DD"
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Probe DTN DataConnect row detection without downloading reports."
    )

    parser.add_argument(
        "--supplier",
        required=True,
        choices=["citgo", "valero"],
        help="Supplier target to find in DTN DataConnect.",
    )

    parser.add_argument(
        "--business-date",
        type=parse_business_date,
        default=date.today() - timedelta(days=1),
        help="Business date to select in DTN dropdown. Format: YYYY-MM-DD.",
    )

    parser.add_argument(
        "--login-url",
        default=None,
        help="Optional DTN login URL override.",
    )

    parser.add_argument(
        "--print-page-text",
        action="store_true",
        help="Print visible page text for debugging row detection.",
    )

    parser.add_argument(
        "--pause",
        action="store_true",
        help="Pause Playwright after row detection for manual inspection.",
    )

    parser.add_argument(
        "--dataconnect-url",
        default=None,
        help="Optional DTN DataConnect URL override.",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    settings = get_settings()
    load_local_env(settings.project_root)

    portal_rule = get_dtn_portal_rule()
    login_url = args.login_url or portal_rule.login_url

    dataconnect_url = (
            args.dataconnect_url
            or portal_rule.dataconnect_url
            or DEFAULT_DTN_DATACONNECT_URL
    )

    account = get_supplier_account(args.supplier)
    credentials = load_credentials(account)
    target = get_dtn_report_target(account.supplier_name)

    print(f"[INFO] supplier={account.supplier_name}")
    print(f"[INFO] portal={account.portal_name}")
    print(f"[INFO] login_url={login_url}")
    print(f"[INFO] dataconnect_url={dataconnect_url}")
    print(f"[INFO] business_date={args.business_date}")
    print(
        "[INFO] target="
        f"name='{target.report_name}', "
        f"group='{target.report_group}', "
        f"document='{target.document_name}'"
    )

    try:
        with open_browser_session(
            account=account,
            settings=settings,
            record_trace=False,
        ) as session:
            page = session.page

            print("[STEP] Logging into DTN...")
            login_to_dtn(
                page=page,
                login_url=login_url,
                username=credentials.username,
                password=credentials.password,
            )

            print(f"[INFO] after_login_url={page.url}")
            print(f"[INFO] after_login_title={page.title()}")
            print("[INFO] authenticated session detected")

            print("[STEP] Opening DataConnect using authenticated session...")
            open_dataconnect_direct(
                page=page,
                dataconnect_url=dataconnect_url,
            )

            print(f"[INFO] current_dataconnect_url={page.url}")
            print(f"[INFO] dataconnect_title={page.title()}")

            print("[STEP] Selecting date...")
            selected_label = select_dataconnect_date(
                page=page,
                business_date=args.business_date,
            )
            print(f"[INFO] selected_date_label={selected_label}")

            print("[STEP] Waiting for DataConnect rows after date change...")
            wait_for_dataconnect_rows(
                page=page,
                target=target,
                timeout_seconds=60,
            )

            if args.print_page_text:
                print("\n========== PAGE TEXT START ==========")
                print(get_visible_table_like_text(page))
                print("========== PAGE TEXT END ==========\n")

            print("[STEP] Finding target report row...")
            row = find_report_row_by_text(page, target)

            if row is None:
                print("[FAILED] Target report row was not found.")
                capture_failure_artifacts(
                    page=page,
                    settings=settings,
                    account=account,
                    step_name="dtn_target_row_not_found",
                )
                return 1

            row_text = " ".join(row.inner_text(timeout=5000).split())
            print("[SUCCESS] Target report row found.")
            print(f"[ROW] {row_text}")

            if args.pause:
                print("[INFO] Pausing for manual inspection.")
                page.pause()

            return 0

    except Exception as exc:
        print(f"[FAILED] DTN DataConnect probe failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())