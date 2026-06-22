from pathlib import Path


def calculate_sha256(file_path: Path, chunk_size: int = 1024 * 1024) -> str:
    """
    Calculate SHA-256 hash for a file.

    Used to detect duplicate downloaded reports and create an audit trail.
    """
    import hashlib

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Cannot hash missing file: {path}")

    if not path.is_file():
        raise ValueError(f"Cannot hash non-file path: {path}")

    sha256 = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(chunk_size), b""):
            sha256.update(chunk)

    return sha256.hexdigest()