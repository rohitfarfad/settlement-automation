from _path_setup import PROJECT_ROOT  # noqa: F401

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
from pprint import pprint

from config.settings import get_settings
from settlement_automation.services.excel_writer import write_parsed_report_to_excel
from settlement_automation.services.report_processor import parse_report
from settlement_automation.services.validation import validate_report


def parse_iso_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid date: {value}. Expected YYYY-MM-DD."
        ) from exc


def iter_dates(start_date: date, end_date: date):
    current = start_date

    while current <= end_date:
        yield current
        current += timedelta(days=1)


def get_raw_report_path(
    *,
    raw_root: Path,
    supplier: str,
    business_date: date,
) -> Path:
    supplier = supplier.lower()

    return (
        raw_root
        / supplier
        / f"{business_date.year:04d}"
        / f"{business_date.month:02d}"
        / f"{supplier}_{business_date.isoformat()}.txt"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Excel writer for parsed raw supplier reports over a date range."
    )

    parser.add_argument(
        "--supplier",
        default="valero",
        choices=["valero", "citgo", "sunoco"],
        help="Supplier to process. Default: valero.",
    )

    parser.add_argument(
        "--start-date",
        required=True,
        type=parse_iso_date,
        help="Start date inclusive, format YYYY-MM-DD.",
    )

    parser.add_argument(
        "--end-date",
        required=True,
        type=parse_iso_date,
        help="End date inclusive, format YYYY-MM-DD.",
    )

    parser.add_argument(
        "--raw-root",
        type=Path,
        default=Path("data/raw"),
        help="Root folder for raw reports. Default: data/raw.",
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
        help="Folder where copied workbooks/backups are written.",
    )

    parser.add_argument(
        "--write",
        action="store_true",
        help="Actually write Excel updates. Without this, runs in dry-run mode.",
    )

    parser.add_argument(
        "--write-originals",
        action="store_true",
        help="Write directly into workbooks under workbook-root.",
    )

    parser.add_argument(
        "--no-backup-originals",
        action="store_true",
        help="Do not create backups when using --write-originals.",
    )

    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue processing later dates if one date fails.",
    )

    parser.add_argument(
        "--skip-missing",
        action="store_true",
        help="Skip missing raw files instead of treating them as failures.",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()
    settings = get_settings()

    if args.start_date > args.end_date:
        print("[FAILED] --start-date cannot be after --end-date.")
        return 1

    if args.write_originals and not args.write:
        print("[FAILED] --write-originals requires --write.")
        return 1

    raw_root = args.raw_root
    workbook_root = args.workbook_root or settings.excel_workbook_root
    output_root = args.output_root or settings.excel_output_dir

    print("\nEXCEL RANGE WRITER")
    print("=" * 100)
    print(f"supplier             : {args.supplier.upper()}")
    print(f"start_date           : {args.start_date}")
    print(f"end_date             : {args.end_date}")
    print(f"raw_root             : {raw_root}")
    print(f"workbook_root        : {workbook_root}")
    print(f"output_root          : {output_root}")
    print(f"dry_run              : {not args.write}")
    print(f"write_originals      : {args.write_originals}")
    print(f"backup_originals     : {not args.no_backup_originals}")
    print("=" * 100)

    processed = 0
    skipped = 0
    failed = 0
    total_written = 0
    total_warnings = 0

    for current_date in iter_dates(args.start_date, args.end_date):
        print(f"\n\nPROCESSING DATE: {current_date}")
        print("-" * 100)

        raw_file = get_raw_report_path(
            raw_root=raw_root,
            supplier=args.supplier,
            business_date=current_date,
        )

        print(f"raw_file: {raw_file}")

        if not raw_file.exists():
            message = f"Raw file not found: {raw_file}"

            if args.skip_missing:
                print(f"[SKIPPED] {message}")
                skipped += 1
                continue

            print(f"[FAILED] {message}")
            failed += 1

            if not args.continue_on_error:
                break

            continue

        try:
            print("[STEP] Parsing raw report...")
            report = parse_report(str(raw_file))

            print("[STEP] Validating parsed report...")
            validation_result = validate_report(report)

            print("\nPARSED REPORT SUMMARY")
            print(f"supplier                     : {report.supplier}")
            print(f"report_date                  : {report.report_date}")
            print(f"daily_totals                 : {len(report.daily_totals)}")
            print(f"mobile_adjustments           : {len(report.mobile_adjustments)}")
            print(
                "valero_pay_plus_adjustments : "
                f"{len(getattr(report, 'valero_pay_plus_adjustments', []))}"
            )

            print("\nVALIDATION")
            print(f"is_valid: {validation_result.is_valid}")

            if validation_result.issues:
                pprint(validation_result.issues)

            if not validation_result.is_valid:
                print("[FAILED] Validation failed. Excel write skipped.")
                failed += 1

                if not args.continue_on_error:
                    break

                continue

            print("\n[STEP] Running Excel writer...")
            result = write_parsed_report_to_excel(
                report=report,
                workbook_root=workbook_root,
                output_root=output_root,
                dry_run=not args.write,
                write_originals=args.write_originals,
                backup_originals=not args.no_backup_originals,
            )

            processed += 1
            total_written += result.written_count
            total_warnings += len(result.warnings)

            print("\n[DATE COMPLETE]")
            print(f"date          : {current_date}")
            print(f"written_count : {result.written_count}")
            print(f"skipped_count : {result.skipped_count}")
            print(f"warnings      : {len(result.warnings)}")

        except Exception as exc:
            print(f"[FAILED] Date {current_date} failed: {exc}")
            failed += 1

            if not args.continue_on_error:
                break

    print("\n\nRANGE SUMMARY")
    print("=" * 100)
    print(f"processed_dates : {processed}")
    print(f"skipped_dates   : {skipped}")
    print(f"failed_dates    : {failed}")
    print(f"total_written   : {total_written}")
    print(f"total_warnings  : {total_warnings}")
    print("=" * 100)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
