import re
from pathlib import Path


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def sanitize_filename_part(value: str) -> str:
    """
    Convert arbitrary supplier/report names into safe filename components.
    """
    cleaned = value.strip().lower()
    cleaned = re.sub(r"[^a-z0-9_.-]+", "_", cleaned)
    cleaned = cleaned.strip("._")

    return cleaned or "unknown"


def get_file_size_bytes(path: Path) -> int:
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Cannot get size for missing file: {path}")

    return path.stat().st_size