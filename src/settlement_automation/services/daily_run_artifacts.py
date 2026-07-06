from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from config.settings import get_settings
from settlement_automation.services.daily_pipeline import DailyPipelineResult


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, Path):
        return str(value)

    if is_dataclass(value):
        return asdict(value)

    return str(value)


def _safe_getattr(value: Any, name: str, default: Any = None) -> Any:
    return getattr(value, name, default)


def daily_pipeline_result_to_dict(result: DailyPipelineResult) -> dict[str, Any]:
    summary = result.summary
    notification = result.notification_result

    return {
        "report_date": summary.report_date,
        "run_date": summary.run_date,
        "started_at": summary.started_at,
        "finished_at": summary.finished_at,
        "status": _status_from_summary(result),
        "counts": {
            "suppliers_parsed": len(summary.supplier_names),
            "daily_totals": summary.daily_total_count,
            "mobile_adjustments": summary.mobile_adjustment_count,
            "valero_pay_plus": summary.valero_pay_plus_count,
            "valero_monthly_charges": summary.valero_monthly_charge_count,
            "unclassified_adjustments": summary.unclassified_adjustment_count,
            "warnings": summary.warning_count,
            "errors": summary.error_count,
            "excel_written": summary.excel_written_count,
            "excel_skipped": summary.excel_skipped_count,
        },
        "fetch_results": [
            {
                "supplier_name": _safe_getattr(fetch_result, "supplier_name"),
                "portal_name": _safe_getattr(fetch_result, "portal_name"),
                "status": _safe_getattr(fetch_result, "status"),
                "succeeded": _safe_getattr(fetch_result, "succeeded"),
                "raw_paths": _safe_getattr(fetch_result, "raw_paths", []),
                "error_message": _safe_getattr(fetch_result, "error_message"),
            }
            for fetch_result in summary.fetch_results
        ],
        "parsed_reports": [
            {
                "supplier": report.supplier,
                "daily_total_count": len(report.daily_totals),
                "mobile_adjustment_count": len(report.mobile_adjustments),
                "valero_pay_plus_count": len(
                    getattr(report, "valero_pay_plus_adjustments", []) or []
                ),
                "valero_monthly_charge_count": len(
                    getattr(report, "valero_monthly_charges", []) or []
                ),
                "unclassified_adjustment_count": len(
                    getattr(report, "unclassified_adjustments", []) or []
                ),
            }
            for report in summary.parsed_reports
        ],
        "excel_results": [
            {
                "written_count": _safe_getattr(excel_result, "written_count", 0),
                "skipped_count": _safe_getattr(excel_result, "skipped_count", 0),
                "dry_run": _safe_getattr(excel_result, "dry_run"),
                "write_originals": _safe_getattr(excel_result, "write_originals"),
                "warnings": _safe_getattr(excel_result, "warnings", []),
            }
            for excel_result in summary.excel_results
        ],
        "warnings": list(summary.warnings),
        "anomalies": [
            {
                "code": _safe_getattr(anomaly, "code"),
                "message": _safe_getattr(anomaly, "message"),
                "supplier": _safe_getattr(anomaly, "supplier"),
                "location_id": _safe_getattr(anomaly, "location_id"),
                "location_name": _safe_getattr(anomaly, "location_name"),
                "transaction_date": _safe_getattr(anomaly, "transaction_date"),
                "amount": _safe_getattr(anomaly, "amount"),
            }
            for anomaly in summary.anomalies
        ],
        "errors": [
            {
                "stage": error.stage,
                "supplier": error.supplier,
                "location_id": error.location_id,
                "location_name": error.location_name,
                "message": error.message,
                "exception_type": error.exception_type,
            }
            for error in summary.errors
        ],
        "notification": None
        if notification is None
        else {
            "enabled": notification.enabled,
            "mode": notification.mode,
            "provider": notification.provider,
            "sent": notification.sent,
            "preview_text_path": notification.preview_text_path,
            "preview_html_path": notification.preview_html_path,
            "error_message": notification.error_message,
        },
    }


def _status_from_summary(result: DailyPipelineResult) -> str:
    summary = result.summary
    notification = result.notification_result

    if summary.has_errors:
        return "error"

    if notification and notification.error_message:
        return "error"

    if summary.has_warnings:
        return "warning"

    return "success"


def write_daily_run_artifact(result: DailyPipelineResult) -> Path:
    settings = get_settings()

    summary = result.summary
    report_date_text = summary.report_date.isoformat()
    started_text = summary.started_at.strftime("%Y%m%d_%H%M%S")

    output_dir = settings.output_dir / "daily_runs" / report_date_text
    output_dir.mkdir(parents=True, exist_ok=True)

    artifact_path = output_dir / f"daily_run_{report_date_text}_{started_text}.json"
    latest_path = settings.output_dir / "daily_runs" / "latest.json"

    payload = daily_pipeline_result_to_dict(result)

    artifact_path.write_text(
        json.dumps(payload, indent=2, default=_json_default),
        encoding="utf-8",
    )

    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(
        json.dumps(payload, indent=2, default=_json_default),
        encoding="utf-8",
    )

    return artifact_path