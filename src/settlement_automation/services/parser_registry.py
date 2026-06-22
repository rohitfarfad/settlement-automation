from dataclasses import dataclass
from typing import Callable

from settlement_automation.models import ParsedReport
from settlement_automation.parsers.valero_parser import parse_valero_report
from settlement_automation.parsers.citgo_parser import parse_citgo_report
from settlement_automation.parsers.sunoco_parser import parse_sunoco_report

@dataclass(frozen=True)
class RegisteredParser:
    supplier: str
    detector: Callable[[str], bool]
    parser: Callable[[str], ParsedReport]


def is_valero_report(text: str) -> bool:
    text = text.upper()
    return "VALERO" in text and "JOBBER" in text and "DEALER CREDITS" in text

def is_citgo_report(text: str) -> bool:
    text = text.upper()
    return (
        "CITGO PETROLEUM" in text
        and "CITGO DAILY RECEIVED TRANSACTION SUMMARY" in text
    )

def is_sunoco_report(text: str) -> bool:
    upper_text = text.upper()

    return (
        "SETTLEMENTSUMMARY" in upper_text
        and "SETTLEMENTDATE" in upper_text
        and "TOTALSALESAMOUNT" in upper_text
        and "TOTALADJUSTEDNETAMOUNT" in upper_text
        and "SHIPTONUMBER" in upper_text
    )


PARSERS = [
    RegisteredParser(
        supplier="VALERO",
        detector=is_valero_report,
        parser=parse_valero_report,
    ),
    RegisteredParser(
        supplier="CITGO",
        detector=is_citgo_report,
        parser=parse_citgo_report,
    ),
    RegisteredParser(
        supplier="SUNOCO",
        detector=is_sunoco_report,
        parser=parse_sunoco_report,
    ),
]


def get_parser_for_text(text: str) -> RegisteredParser:
    matches = [parser for parser in PARSERS if parser.detector(text)]

    if not matches:
        raise ValueError("No matching parser found for this report")

    if len(matches) > 1:
        suppliers = [parser.supplier for parser in matches]
        raise ValueError(f"Multiple parsers matched this report: {suppliers}")

    return matches[0]