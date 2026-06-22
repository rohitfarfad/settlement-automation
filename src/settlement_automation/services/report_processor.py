from pathlib import Path

from settlement_automation.models import ParsedReport
from settlement_automation.services.parser_registry import get_parser_for_text
from settlement_automation.utils.text import load_normalized_text


def parse_report(file_path: str) -> ParsedReport:
    """
    Main parser entrypoint.

    The fetching pipeline should call only this function.
    """
    text = load_normalized_text(file_path)
    parser = get_parser_for_text(text)
    return parser.parser(file_path)