import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"


def add_project_paths() -> None:
    """
    Allows scripts/ files to import both:
    - top-level config/
    - src/settlement_automation/
    """
    for path in (PROJECT_ROOT, SRC_DIR):
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)


add_project_paths()