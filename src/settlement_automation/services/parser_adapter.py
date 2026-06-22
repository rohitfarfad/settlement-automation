from dataclasses import asdict, is_dataclass
from importlib import import_module
from pathlib import Path
from pprint import pformat
from typing import Any

from settlement_automation.exceptions import SettlementAutomationError


class ParserInvocationError(SettlementAutomationError):
    """Raised when the parser adapter cannot call the existing parser."""


def _class_name_for_supplier(supplier_name: str) -> str:
    return f"{supplier_name.capitalize()}Parser"


def parse_report_with_existing_parser(
    supplier_name: str,
    file_path: Path,
) -> Any:
    """
    Call the existing supplier parser without forcing a parser refactor.

    Supports common existing patterns:
    - CitgoParser().parse(path)
    - CitgoParser().parse_file(path)
    - parse_citgo_report(path)
    - parse_report(path)
    - parse(path)
    - parse_file(path)
    """
    supplier_key = supplier_name.lower()
    file_path = Path(file_path)

    module_name = f"settlement_automation.parsers.{supplier_key}_parser"
    module = import_module(module_name)

    class_name = _class_name_for_supplier(supplier_key)

    if hasattr(module, class_name):
        parser = getattr(module, class_name)()

        for method_name in ("parse", "parse_file"):
            if hasattr(parser, method_name):
                return getattr(parser, method_name)(file_path)

    function_candidates = [
        f"parse_{supplier_key}_report",
        "parse_report",
        "parse_file",
        "parse",
    ]

    for function_name in function_candidates:
        if hasattr(module, function_name):
            return getattr(module, function_name)(file_path)

    raise ParserInvocationError(
        f"Could not find parser entry point for supplier={supplier_name}. "
        f"Checked module={module_name}, class={class_name}, "
        f"functions={function_candidates}"
    )


def make_result_displayable(result: Any) -> Any:
    """
    Convert parser output into something printable.
    """
    if is_dataclass(result):
        return asdict(result)

    if hasattr(result, "model_dump"):
        return result.model_dump()

    if hasattr(result, "dict"):
        return result.dict()

    if isinstance(result, (dict, list, tuple, str, int, float, bool, type(None))):
        return result

    if hasattr(result, "__dict__"):
        return result.__dict__

    return repr(result)


def format_parsed_result(result: Any) -> str:
    return pformat(make_result_displayable(result), width=120)