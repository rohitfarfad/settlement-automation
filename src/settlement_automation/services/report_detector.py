from pathlib import Path

from settlement_automation.services.parser_registry import get_parser_for_text


def detect_supplier(file_path: str) -> str:
    text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    return get_parser_for_text(text).supplier