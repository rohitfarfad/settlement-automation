from _path_setup import PROJECT_ROOT  # noqa: F401

import argparse
from datetime import date, timedelta
from pathlib import Path

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
    find_matching_report_rows_by_text,
    get_visible_table_like_text,
    login_to_dtn,
    open_dataconnect_direct,
    select_dataconnect_date,
    wait_for_dataconnect_rows,
)
from settlement_automation.utils.env import load_local_env
from settlement_automation.utils.files import ensure_directory, sanitize_filename_part


def parse_business_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid date: {value}. Expected format: YYYY-MM-DD"
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Probe DTN row-click report capture without parsing or Excel output."
    )

    parser.add_argument(
        "--supplier",
        required=True,
        choices=["citgo", "valero"],
    )

    parser.add_argument(
        "--business-date",
        type=parse_business_date,
        default=date.today() - timedelta(days=1),
    )

    parser.add_argument(
        "--row-number",
        type=int,
        default=1,
        help="Which matching row to click. CITGO may have multiple matching rows.",
    )

    parser.add_argument(
        "--login-url",
        default=None,
    )

    parser.add_argument(
        "--dataconnect-url",
        default=None,
    )

    parser.add_argument(
        "--pause-after-click",
        action="store_true",
        help="Pause after clicking the row so you can inspect the report page.",
    )

    return parser


def build_capture_path(settings, supplier_name: str, business_date: date, row_number: int) -> Path:
    supplier = sanitize_filename_part(supplier_name)
    date_text = business_date.isoformat()

    output_dir = settings.tmp_download_dir / "dtn" / supplier / date_text
    ensure_directory(output_dir)

    return output_dir / f"{supplier}_click_capture_{date_text}_row_{row_number}.txt"


def get_best_visible_report_text(page) -> str:
    """
    Try common report containers first, then fall back to full body text.
    """
    selectors = [
        "pre",
        "textarea",
        "[id*='message' i]",
        "[id*='report' i]",
        "[class*='message' i]",
        "[class*='report' i]",
        "body",
    ]

    best_text = ""

    for selector in selectors:
        locator = page.locator(selector)

        try:
            count = locator.count()
        except Exception:
            continue

        for index in range(count):
            item = locator.nth(index)

            try:
                if not item.is_visible():
                    continue
            except Exception:
                pass

            try:
                text = item.inner_text(timeout=5000)
            except Exception:
                continue

            text = text.strip()

            if len(text) > len(best_text):
                best_text = text

    return best_text


def click_matching_row(row):
    """
    DTN appears to use JavaScript click behavior rather than normal href links.
    Try the most likely clickable cells first.
    """
    candidates = []

    try:
        cells = row.locator("td")
        cell_count = cells.count()

        if cell_count > 0:
            candidates.append(cells.nth(0))  # Supplier/report name cell

        if cell_count > 3:
            candidates.append(cells.nth(3))  # Document cell

    except Exception:
        pass

    candidates.append(row)

    last_error = None

    for candidate in candidates:
        try:
            candidate.click(force=True, timeout=10000)
            return
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"Could not click matching DTN row. Last error: {last_error}")


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
    print(f"[INFO] login_url={login_url}")
    print(f"[INFO] dataconnect_url={dataconnect_url}")
    print(f"[INFO] business_date={args.business_date}")
    print(f"[INFO] row_number={args.row_number}")

    try:
        with open_browser_session(
            account=account,
            settings=settings,
            record_trace=False,
        ) as session:
            page = session.page

            response_urls = []

            def record_response(response):
                url = response.url
                if "fuelbuyer.dtn.com/energy" in url:
                    response_urls.append(url)

            page.on("response", record_response)

            print("[STEP] Logging into DTN...")
            login_to_dtn(
                page=page,
                login_url=login_url,
                username=credentials.username,
                password=credentials.password,
            )

            print("[STEP] Opening DataConnect...")
            open_dataconnect_direct(
                page=page,
                dataconnect_url=dataconnect_url,
            )

            print("[STEP] Selecting date...")
            selected_label = select_dataconnect_date(
                page=page,
                business_date=args.business_date,
            )
            print(f"[INFO] selected_date_label={selected_label}")

            print("[STEP] Waiting for rows...")
            wait_for_dataconnect_rows(
                page=page,
                target=target,
                timeout_seconds=60,
            )

            rows = find_matching_report_rows_by_text(page, target)
            print(f"[INFO] matching_rows_found={len(rows)}")

            for index, row in enumerate(rows, start=1):
                row_text = " ".join(row.inner_text(timeout=5000).split())
                print(f"[ROW {index}] {row_text}")

            if not rows:
                print("[FAILED] No matching rows found.")
                return 1

            if args.row_number < 1 or args.row_number > len(rows):
                print(
                    f"[FAILED] Invalid row number {args.row_number}. "
                    f"Available rows: 1 to {len(rows)}"
                )
                return 1

            row = rows[args.row_number - 1]

            before_url = page.url
            before_page_count = len(page.context.pages)

            print("[STEP] Clicking matching report row...")
            click_matching_row(row)

            page.wait_for_timeout(5000)

            pages = page.context.pages
            report_page = page

            if len(pages) > before_page_count:
                report_page = pages[-1]
                print("[INFO] Report opened in a new tab/window.")
            else:
                print("[INFO] Report appears to have opened in the same tab/page.")

            try:
                report_page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass

            print(f"[INFO] before_click_url={before_url}")
            print(f"[INFO] after_click_url={report_page.url}")
            print(f"[INFO] after_click_title={report_page.title()}")

            if args.pause_after_click:
                print("[INFO] Pausing after click for manual inspection.")
                report_page.pause()

            print("[STEP] Capturing visible report text...")
            report_text = get_best_visible_report_text(report_page)

            if not report_text.strip():
                print("[FAILED] No visible report text captured.")
                capture_failure_artifacts(
                    page=report_page,
                    settings=settings,
                    account=account,
                    step_name="dtn_click_capture_empty",
                )
                return 1

            output_path = build_capture_path(
                settings=settings,
                supplier_name=account.supplier_name,
                business_date=args.business_date,
                row_number=args.row_number,
            )

            output_path.write_text(report_text, encoding="utf-8")

            print("[SUCCESS] Captured visible DTN report text.")
            print(f"[INFO] output_path={output_path}")
            print(f"[INFO] size_bytes={output_path.stat().st_size}")

            print("[INFO] Recent DTN response URLs seen during click:")
            for url in response_urls[-20:]:
                print(f"  {url}")

            return 0

    except Exception as exc:
        print(f"[FAILED] DTN click capture probe failed: {exc}")

        try:
            capture_failure_artifacts(
                page=page,
                settings=settings,
                account=account,
                step_name="dtn_click_capture_failed",
            )
        except Exception:
            pass

        return 1


if __name__ == "__main__":
    raise SystemExit(main())