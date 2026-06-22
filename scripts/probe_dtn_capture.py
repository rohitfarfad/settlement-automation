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
from settlement_automation.connectors.dtn_capture import fetch_dtn_report_url_to_tmp_file
from settlement_automation.connectors.dtn_page import (
    extract_matching_dtn_report_links,
    find_matching_report_rows_by_text,
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
        description="Probe DTN report content capture without parsing or Excel output."
    )

    parser.add_argument(
        "--supplier",
        required=True,
        choices=["citgo", "valero"],
        help="Supplier target to capture from DTN DataConnect.",
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
        "--dataconnect-url",
        default=None,
        help="Optional DTN DataConnect URL override.",
    )

    parser.add_argument(
        "--print-page-text",
        action="store_true",
        help="Print visible page text for debugging.",
    )

    parser.add_argument(
        "--pause-before-capture",
        action="store_true",
        help="Pause before fetching report links.",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    settings = get_settings()
    load_local_env(settings.project_root)

    portal_rule = get_dtn_portal_rule()
    login_url = args.login_url or portal_rule.login_url
    dataconnect_url = args.dataconnect_url or portal_rule.dataconnect_url

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

            print("[STEP] Waiting for DataConnect rows...")
            wait_for_dataconnect_rows(
                page=page,
                target=target,
                timeout_seconds=60,
            )

            if args.print_page_text:
                print("\n========== PAGE TEXT START ==========")
                print(get_visible_table_like_text(page))
                print("========== PAGE TEXT END ==========\n")

            rows = find_matching_report_rows_by_text(page, target)
            print(f"[INFO] matching_rows_found={len(rows)}")

            for index, row in enumerate(rows, start=1):
                row_text = " ".join(row.inner_text(timeout=5000).split())
                print(f"[ROW {index}] {row_text}")

            print("[STEP] Extracting report links from matching rows...")
            report_links = extract_matching_dtn_report_links(
                page=page,
                target=target,
                business_date=args.business_date,
            )

            print(f"[INFO] report_links_found={len(report_links)}")

            for link in report_links:
                print(f"[LINK {link.row_index}] {link.url}")

            if not report_links:
                print("[FAILED] No report links found in matching DTN rows.")
                capture_failure_artifacts(
                    page=page,
                    settings=settings,
                    account=account,
                    step_name="dtn_report_links_not_found",
                )
                return 1

            if args.pause_before_capture:
                print("[INFO] Pausing before capture.")
                page.pause()

            print("[STEP] Fetching report URLs using authenticated session...")
            captured_reports = []

            for report_link in report_links:
                captured = fetch_dtn_report_url_to_tmp_file(
                    page=page,
                    report_link=report_link,
                    account=account,
                    target=target,
                    settings=settings,
                )
                captured_reports.append(captured)

            print("[SUCCESS] Captured DTN report responses.")

            for report in captured_reports:
                print(f"  row_index={report.row_index}")
                print(f"  source_url={report.source_url}")
                print(f"  tmp_path={report.tmp_path}")
                print(f"  size_bytes={report.size_bytes}")

            return 0

    except Exception as exc:
        print(f"[FAILED] DTN capture probe failed: {exc}")

        try:
            capture_failure_artifacts(
                page=page,
                settings=settings,
                account=account,
                step_name="dtn_capture_failed",
            )
        except Exception:
            pass

        return 1


if __name__ == "__main__":
    raise SystemExit(main())