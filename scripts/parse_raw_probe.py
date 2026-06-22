from _path_setup import PROJECT_ROOT  # noqa: F401

import argparse
from pathlib import Path
from pprint import pprint

from settlement_automation.services.report_processor import parse_report
from settlement_automation.services.validation import validate_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse one raw supplier report using the official parser pipeline."
    )

    parser.add_argument(
        "--file",
        required=True,
        type=Path,
        help="Path to raw report file.",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    print(f"[INFO] raw_file={args.file}")

    report = parse_report(str(args.file))
    validation_result = validate_report(report)

    print("[SUCCESS] parse_report completed.")

    print("\n========== PARSED DAILY TOTALS ==========")
    pprint(getattr(report, "daily_totals", None))

    print("\n========== MOBILE ADJUSTMENTS ==========")
    pprint(getattr(report, "mobile_adjustments", None))

    print("\n========== VALIDATION ==========")
    print(f"is_valid={validation_result.is_valid}")
    pprint(validation_result.issues)

    if not validation_result.is_valid:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())