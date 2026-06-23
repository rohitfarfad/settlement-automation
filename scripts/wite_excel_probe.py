from _path_setup import PROJECT_ROOT  # noqa: F401

import argparse
from pathlib import Path
from pprint import pprint

from config.settings import get_settings
from settlement_automation.services.excel_writer import write_parsed_report_to_excel
from settlement_automation.services.report_processor import parse_report
from settlement_automation.services.validation import validate_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse a raw report and preview Excel write operations."
    )
    parser.add_argument(
        "--file",
        required=True,
        type=Path,
        help="Raw supplier report file to parse.",
    )
    parser.add_argument(
        "--workbook-root",
        type=Path,
        default=None,
        help="Folder containing location Excel workbooks.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Folder where updated workbook copies will be written later.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    settings = get_settings()

    workbook_root = args.workbook_root or settings.excel_workbook_root
    output_root = args.output_root or settings.excel_output_dir

    print("[STEP] Parsing raw report...")
    report = parse_report(str(args.file))

    print("[STEP] Validating parsed report...")
    validation_result = validate_report(report)

    print("\n========== PARSED REPORT SUMMARY ==========")
    print(f"supplier={report.supplier}")
    print(f"report_date={report.report_date}")
    print(f"daily_totals={len(report.daily_totals)}")
    print(f"mobile_adjustments={len(report.mobile_adjustments)}")

    print("\n========== VALIDATION ==========")
    print(f"is_valid={validation_result.is_valid}")
    pprint(validation_result.issues)

    if not validation_result.is_valid:
        print("[FAILED] Validation failed. Excel preview skipped.")
        return 1

    print("\n[STEP] Building Excel write preview...")
    write_parsed_report_to_excel(
        report=report,
        workbook_root=workbook_root,
        output_root=output_root,
        dry_run=True,
    )

    print("\n[SUCCESS] Excel write preview completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())