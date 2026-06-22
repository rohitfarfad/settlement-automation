import html
import re
from pathlib import Path


def load_normalized_text(file_path: str | Path) -> str:
    """
    Load report text in a parser-friendly way.

    Supports:
    - plain fixed-width text reports
    - simple HTML wrappers containing <pre> report text
    - copied visible report text from DTN
    """
    text = Path(file_path).read_text(encoding="utf-8", errors="ignore")

    # Decode HTML entities like &amp;, &nbsp;, etc.
    text = html.unescape(text)

    # Convert non-breaking spaces to regular spaces.
    text = text.replace("\xa0", " ")

    # Normalize line endings.
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove common wrapper tags while preserving inner text.
    text = re.sub(
        r"</?(table|tr|td|pre|html|body)[^>]*>",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Remove form-feed page breaks from fixed-width reports.
    text = text.replace("\f", "\n")

    return text